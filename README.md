# se-1151-project

## 啟動與資料庫設定

使用 Python 3.10 以上版本。先建立 PostgreSQL 資料庫，並為專案設定連線字串。需要共用帳號與教室資料的 API 執行個體，請指向同一個資料庫。

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL = 'postgresql://app_user:password@localhost:5432/se1151'
python -m db init
python -m db create-admin admin
python -m uvicorn main:app
```

請以實際連線資訊取代範例。`db init` 會建立 `users`、`rooms` 和 `auth_sessions`。`create-admin` 會提示輸入密碼，新建的管理員可立即登入。帳號使用 3 至 50 個英文字母、數字或 `_.-`，儲存時統一為小寫。新密碼長度為 12 至 128 字元。

## 共用 API

啟動後可在 `/docs` 操作。註冊與登入皆傳送 JSON `{"username":"…","password":"…"}`。登入回應中的 `access_token` 用於 `Authorization: Bearer <token>`，效期為 8 小時。登出會撤銷本次登入的 token。

| 方法與路徑 | 用途 |
| --- | --- |
| `POST /auth/register` | 註冊普通帳號，狀態為 `pending` |
| `POST /auth/login` | 已審核通過的帳號可取得 token |
| `GET /auth/me` | 查詢目前登入者 |
| `POST /auth/logout` | 撤銷目前的 token |
| `GET /admin/users/pending` | 管理員查詢待審核帳號 |
| `PATCH /admin/users/{user_id}/review` | 管理員送出 `{"status":"approved"}` 或 `{"status":"rejected"}` |
| `PATCH /admin/users/{user_id}/role` | 管理員送出 `{"role":"teacher"}`，將已核准的一般帳號設為教師 |
| `GET /rooms` | 已登入使用者查詢教室 |

教室資料可由資料庫維護，例如 `INSERT INTO rooms (code, name, capacity) VALUES ('A101', 'A101 教室', 40);`。

既有資料庫可重新執行 `python -m db init`，更新帳號角色限制並保留原有資料。公開註冊仍建立待審核的 `user` 帳號。
