"""家族カレンダー API サーバー"""

import os
import json
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
import db

app = Flask(__name__)

# CORS設定：Netlifyのフロントエンドからのアクセスを許可
# デプロイ後、FRONTEND_URL 環境変数に Netlify の URL を設定してください
# 例: https://kazoku-calendar.netlify.app
frontend_url = os.environ.get("FRONTEND_URL", "*")
CORS(app, origins=frontend_url.split(","), supports_credentials=True)

# 家族用パスワード（環境変数で設定）
FAMILY_PASSWORD = os.environ.get("FAMILY_PASSWORD", "kazoku2026")

# DB初期化
db.init_db()


# ========================================
# 認証ミドルウェア
# ========================================
def require_auth(f):
    """リクエストヘッダーの X-Family-Password を検証"""
    @wraps(f)
    def decorated(*args, **kwargs):
        password = request.headers.get("X-Family-Password", "")
        if password != FAMILY_PASSWORD:
            return jsonify({"error": "パスワードが正しくありません"}), 401
        return f(*args, **kwargs)
    return decorated


# ========================================
# ヘルスチェック（認証不要）
# ========================================
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "app": "family-calendar-api",
        "time": datetime.utcnow().isoformat()
    })


# ========================================
# パスワード検証
# ========================================
@app.route("/api/auth", methods=["POST"])
def auth():
    """パスワードが正しいか確認するだけ"""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if password == FAMILY_PASSWORD:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "パスワードが正しくありません"}), 401


# ========================================
# 全データ取得（同期ダウンロード）
# ========================================
@app.route("/api/sync", methods=["GET"])
@require_auth
def sync_download():
    """サーバーの全データを返す"""
    members = db.load("members", [])
    events = db.load("events", [])
    settings = db.load("settings", {})
    return jsonify({
        "members": members,
        "events": events,
        "settings": settings,
        "lastSync": datetime.utcnow().isoformat()
    })


# ========================================
# 全データ上書き（同期アップロード）
# ========================================
@app.route("/api/sync", methods=["POST"])
@require_auth
def sync_upload():
    """クライアントのデータでサーバーを上書き"""
    data = request.get_json(silent=True) or {}
    if "members" in data:
        db.save("members", data["members"])
    if "events" in data:
        db.save("events", data["events"])
    if "settings" in data:
        db.save("settings", data["settings"])
    return jsonify({
        "ok": True,
        "lastSync": datetime.utcnow().isoformat()
    })


# ========================================
# スマート同期（競合解決付き）
# ========================================
@app.route("/api/sync/merge", methods=["POST"])
@require_auth
def sync_merge():
    """クライアントとサーバーのデータをマージする

    方針：
    - メンバー：IDベースでマージ（新しい方を優先）
    - 予定：IDベースでマージ（updatedAtが新しい方を優先）
    """
    client_data = request.get_json(silent=True) or {}

    # サーバー側の現在データ
    server_members = db.load("members", [])
    server_events = db.load("events", [])

    # クライアント側のデータ
    client_members = client_data.get("members", [])
    client_events = client_data.get("events", [])

    # メンバーをマージ
    merged_members = _merge_by_id(server_members, client_members, "createdAt")

    # 予定をマージ（updatedAtで新しい方を採用）
    merged_events = _merge_by_id(server_events, client_events, "updatedAt")

    # 保存
    db.save("members", merged_members)
    db.save("events", merged_events)

    # マージ結果を返す
    return jsonify({
        "ok": True,
        "members": merged_members,
        "events": merged_events,
        "lastSync": datetime.utcnow().isoformat(),
        "stats": {
            "members": len(merged_members),
            "events": len(merged_events)
        }
    })


def _merge_by_id(server_list, client_list, timestamp_field):
    """IDベースでリストをマージ。タイムスタンプが新しい方を優先"""
    merged = {}

    # サーバー側を先にセット
    for item in server_list:
        if "id" in item:
            merged[item["id"]] = item

    # クライアント側で上書き（より新しいもののみ）
    for item in client_list:
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id not in merged:
            # サーバーにない → 新規追加
            merged[item_id] = item
        else:
            # 両方にある → タイムスタンプ比較
            server_ts = merged[item_id].get(timestamp_field, "")
            client_ts = item.get(timestamp_field, "")
            if client_ts >= server_ts:
                merged[item_id] = item

    return list(merged.values())


# ========================================
# 起動
# ========================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
