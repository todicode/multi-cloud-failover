# Giai đoạn 2 — Docker hóa ứng dụng

## 1. Mục tiêu và phạm vi

Đóng gói ứng dụng FastAPI Issues thành Linux container image, kiểm tra image với PostgreSQL trong local lab và chuẩn bị cùng một image để triển khai lên AWS/Azure ở các giai đoạn sau.

Tài liệu được bổ sung theo từng bước thực hành. Nội dung hiện bao gồm Dockerfile tối thiểu, cấu hình `.dockerignore`, build image, kiểm tra HTTP, hai container web kết nối PostgreSQL primary/standby và bài kiểm tra dữ liệu qua hai web. Mỗi bước chỉ được xác nhận từ đầu ra thực tế.

Giai đoạn này tập trung vào image ứng dụng và kết nối database. Hạ tầng AWS/Azure, K3s, WireGuard, CI/registry và DNS failover được thực hiện ở các giai đoạn sau.

Điều kiện nghiệm thu khi hoàn thành toàn bộ giai đoạn:

- Build được application image cho Linux AMD64.
- Container phục vụ giao diện, API, identity và health endpoints.
- Truyền cấu hình môi trường và kết nối database khi chạy container.
- Ghi dữ liệu qua ứng dụng nối primary và đọc dữ liệu đã replicate qua ứng dụng nối standby.
- Thông tin xác thực được truyền khi chạy, không ghi cố định trong image.

## 2. Liên hệ với giai đoạn 1

Tham chiếu: [Giai đoạn 1 — Ứng dụng và PostgreSQL replication local](giaidoan1_ungdung_database_local.md).

Ở giai đoạn 1, hai web FastAPI và proxy chạy bằng Python trực tiếp trên Windows; hai PostgreSQL chạy trong Docker containers. Giai đoạn 2 đưa ứng dụng FastAPI vào container, sử dụng lại nghiệp vụ và schema hiện tại.

| Thành phần | Cách sử dụng trong giai đoạn 2 |
|---|---|
| [app/](../../app/) | Mã FastAPI và giao diện cần đóng gói |
| [database/](../../database/) | Mã truy cập PostgreSQL và schema ứng dụng |
| [requirements.txt](../../requirements.txt) | Dependency chạy ứng dụng |
| [database/compose.replication.yml](../../database/compose.replication.yml) | Hai PostgreSQL của local lab |
| [scripts/Use-LocalLab.ps1](../../scripts/Use-LocalLab.ps1) | Cấu hình terminal cho lab hiện tại |
| [scripts/local_replication.py](../../scripts/local_replication.py) | Điều khiển topology và các tiến trình web của giai đoạn 1 |

Dockerfile mô tả cách tạo image ứng dụng. Cấu hình triển khai quyết định image chạy ở đâu, nhận biến môi trường nào, kết nối database nào và được truy cập qua mạng như thế nào.

Mục tiêu là dùng cùng một application image cho hai môi trường; `APP_ENV`, `APP_REGION`, `DATABASE_URL` và thông tin phiên bản được cung cấp theo môi trường chạy. Hai PostgreSQL tiếp tục dùng image `postgres:17` riêng.

## 3. Kiểm tra môi trường

Mở Git Bash tại repository:

```bash
cd /d/multi-cloud-failover
docker version
docker compose version
docker info --format '{{.OSType}}'
```

Kết quả cần có:

- `docker version` hiển thị được cả Client và Server.
- `docker compose version` trả về phiên bản Compose.
- Lệnh cuối trả về `linux`.

Nếu chưa kết nối được Docker Engine, mở Docker Desktop và chờ Engine hoạt động. Nếu Engine dùng Windows containers, chuyển sang Linux containers trước khi tiếp tục.

Lệnh trong tài liệu chạy từ Git Bash trên Windows. Dockerfile và ứng dụng trong image sử dụng môi trường Linux. Không cần mở terminal Ubuntu/WSL; nếu Docker Desktop sử dụng backend WSL 2, backend đó vẫn cần hoạt động.

Helper `Use-LocalLab.ps1` của giai đoạn 1 dành cho PowerShell, không dùng `source` để nạp vào Git Bash. Cấu hình Bash cần thiết cho các bước kết nối database sẽ được bổ sung khi tới phần đó.

## 4. Bước thực hành đầu tiên: nền tảng của image

Tự tạo file tên `Dockerfile`, không có phần mở rộng, tại thư mục gốc repository: `D:\multi-cloud-failover\Dockerfile`.

Có thể tạo file bằng trình soạn thảo hoặc, nếu file chưa tồn tại, chạy trong Git Bash:

```bash
touch Dockerfile
```

Nhập đoạn đầu sau:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
```

| Chỉ thị | Giải thích |
|---|---|
| `FROM python:3.12-slim` | Bắt đầu từ Python 3.12 image với hệ điều hành Linux tối giản |
| `WORKDIR /app` | Chọn `/app` bên trong image làm thư mục làm việc cho các chỉ thị tiếp theo |
| `PYTHONDONTWRITEBYTECODE=1` | Không sinh file bytecode `.pyc` khi import module |
| `PYTHONUNBUFFERED=1` | Xuất stdout/stderr không qua bộ đệm của Python, giúp theo dõi log container |

`/app` là đường dẫn Linux bên trong image, khác với thư mục source trên Windows. `WORKDIR` chưa sao chép mã nguồn vào image.

Đoạn này mới chuẩn bị môi trường nền. Chưa cài dependency, sao chép source hoặc khai báo lệnh chạy FastAPI. Chưa build/chạy ứng dụng ở bước này.

Kiểm tra nội dung đã nhập:

```bash
cat Dockerfile
```

Trước khi sang bước tiếp theo, cần giải thích được:

1. Vì sao image cần Python dù máy Windows đã cài Python?
2. `/app` nằm trong image hay trên máy Windows?
3. Vì sao đoạn Dockerfile hiện tại chưa chạy được web?

## 5. Bước thực hành tiếp theo: build context và .dockerignore

Build context là tập hợp file mà Docker builder được phép truy cập khi build. Khi dùng thư mục hiện tại làm context bằng dấu `.` ở cuối lệnh build, source được lấy từ thư mục đó. Chỉ thị `COPY` sẽ chọn file trong context để đưa vào image; file có trong context không đồng nghĩa tự động nằm trong image.

`.dockerignore` loại các đường dẫn không cần thiết khỏi build context. `.gitignore` quản lý việc Git theo dõi file, không thay thế `.dockerignore` khi build từ thư mục local.

Tại thư mục gốc repository, tự tạo file `.dockerignore` cạnh `Dockerfile`:

```bash
touch .dockerignore
```

Nhập nội dung:

```text
# Git and local Python environment
.git
.venv
venv
**/__pycache__
**/*.py[cod]
.pytest_cache

# Local configuration and runtime output
.env
.env.*
*.pem
*.key
.local-replication
**/*.log

# Documentation, tests and editor settings
docs
images
tests
experiments
.vscode
.idea
```

| Nhóm | Lý do loại khỏi context |
|---|---|
| `.git` | Image chạy ứng dụng không cần lịch sử Git; thông tin commit sẽ được cung cấp riêng |
| `.venv`, `venv` | Không sao chép môi trường Python Windows vào image Linux; dependency sẽ được cài bên trong image |
| Cache Python và pytest | File sinh ra trong quá trình phát triển, không phải source cần đóng gói |
| `.env`, `.env.*`, `*.pem`, `*.key` | Cấu hình riêng và key không phải đầu vào của application image; `.env.example` cũng khớp quy tắc này |
| `.local-replication`, log | State, PID và log của lab trên máy phát triển |
| `docs`, `images`, `tests`, `experiments`, cấu hình editor | Không cần cho runtime ứng dụng ở giai đoạn này |

Giữ `app/`, `database/` và `requirements.txt` trong context vì ứng dụng cần chúng. Giao diện sử dụng tài nguyên trong `app/static/`; thư mục `images/` ở gốc repository phục vụ tài liệu.

`.dockerignore` không xóa file trên máy và không thay đổi trạng thái theo dõi của Git. File `.dockerignore` cần được commit cùng Dockerfile để người khác build với cùng quy tắc.

Kiểm tra nội dung:

```bash
cat .dockerignore
git status --short
```

Nếu hai file mới chưa được commit, Git sẽ hiển thị `?? .dockerignore` và `?? Dockerfile`. Tài liệu đang chỉnh sửa cũng có thể xuất hiện trong danh sách. Đây là kiểm tra nội dung và trạng thái file; tác dụng lọc context sẽ được kiểm tra ở bước build.

Tới đây mới chuẩn bị context; chưa chạy build. Bước sau bổ sung cài dependency và sao chép source vào Dockerfile.

## 6. Cài thư viện Python trong image

Thêm hai dòng sau vào cuối Dockerfile, bên dưới chỉ thị `ENV` đã có:

```dockerfile
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
```

`COPY` lấy `requirements.txt` từ thư mục gốc build context và đặt vào thư mục làm việc `/app`, thành `/app/requirements.txt`. Dấu `./` ở đích là thư mục hiện tại bên trong image theo `WORKDIR`, không phải thư mục trên Windows.

`RUN` thực thi lệnh khi build image. `python -m pip` gọi pip bằng Python của image; `-r requirements.txt` đọc danh sách dependency; `--no-cache-dir` không giữ cache tải package của pip trong layer. Tùy chọn này không tắt Docker build cache.

| Dependency trong requirements.txt | Vai trò |
|---|---|
| `fastapi` | Framework cho API và ứng dụng web |
| `httpx` | HTTP client dùng trong mã project |
| `psycopg[binary]` | Driver kết nối PostgreSQL |
| `prometheus-client` | Xuất metrics ứng dụng |
| `uvicorn[standard]` | ASGI server chạy FastAPI |

Chỉ cài `requirements.txt` cho image chạy ứng dụng. `requirements-dev.txt` bổ sung công cụ phát triển và kiểm thử như pytest; không dùng file này cho bước cài runtime.

Việc cài dependency được đặt trước bước sao chép source. Khi chỉ thay đổi code ứng dụng và các đầu vào trước đó không đổi, Docker có thể tái sử dụng cache của bước cài thư viện. Khi `requirements.txt` thay đổi, bước `COPY` tương ứng và bước cài thư viện cần chạy lại.

Dockerfile sau bước này:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
```

Kiểm tra nội dung đã lưu trong Git Bash:

```bash
cat Dockerfile
```

Chỉnh sửa Dockerfile chưa thực hiện cài đặt. Hai chỉ thị mới chỉ được thực thi khi chạy build ở bước sau. Tới đây chưa sao chép mã ứng dụng hoặc khai báo lệnh khởi động web; bước tiếp theo bổ sung source cần thiết.

## 7. Sao chép mã ứng dụng vào image

Thêm hai dòng sau vào cuối Dockerfile, sau bước cài thư viện:

```dockerfile
COPY app/ ./app/
COPY database/ ./database/
```

Đường dẫn nguồn ở bên trái được tính từ thư mục gốc build context. Đường dẫn đích ở bên phải được tính từ `WORKDIR /app`:

| Nguồn trong repository | Đích trong image | Nội dung |
|---|---|---|
| `app/` | `/app/app/` | FastAPI, routes, giao diện HTML/CSS/JavaScript trong `static/` |
| `database/` | `/app/database/` | Mã Python kết nối/truy vấn PostgreSQL, schema SQL và các file trong thư mục |

Thư mục `/app` ngoài cùng là thư mục làm việc; thư mục `/app/app` là Python package `app` của project. Giữ cấu trúc này để các import như `from app.issues ...` và `from database.connection ...` tìm đúng module.

Ứng dụng đọc static files từ đường dẫn tương đối với `app/main.py`, còn phần khởi tạo schema đọc SQL từ `database/schema/`. Sao chép đầy đủ hai thư mục giữ được các đường dẫn đó.

`database/` trong source không phải nơi lưu dữ liệu thực tế của PostgreSQL. Lệnh `COPY database/ ...` không đưa PostgreSQL server, volume, các issue đã tạo hay WAL của lab vào application image. PostgreSQL tiếp tục chạy bằng container riêng và ứng dụng kết nối tới nó qua `DATABASE_URL`.

Phần cuối Dockerfile sau bước này:

```dockerfile
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY database/ ./database/
```

Kiểm tra nội dung file trong Git Bash:

```bash
cat Dockerfile
```

Các dòng `COPY` chỉ thực hiện khi build; bước này chưa tạo image. Phần tiếp theo cấu hình user chạy ứng dụng và lệnh khởi động FastAPI.

## 8. Tạo user chạy ứng dụng

Thêm vào cuối Dockerfile, sau hai dòng sao chép source:

```dockerfile
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home appuser

USER appuser
```

`RUN` tạo group và user Linux trong image. Group ID và user ID đều là `10001`; `--create-home` tạo thư mục home cho user. Dấu `&&` chỉ chạy `useradd` khi `groupadd` thành công.

`USER appuser` chọn tài khoản chạy các chỉ thị tiếp theo và tiến trình ứng dụng khi khởi động container. Các bước cài thư viện và tạo user phía trên vẫn chạy bằng root của build stage; web chạy bằng user thông thường.

User Linux `appuser` bên trong container khác với tài khoản PostgreSQL dùng trong `DATABASE_URL`. Không cần tạo tài khoản cùng tên trên Windows. Quyền đọc source, import module và đọc static files được kiểm chứng khi chạy image.

## 9. Khai báo cổng và lệnh khởi động FastAPI

Thêm tiếp vào cuối Dockerfile:

```dockerfile
EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

| Thành phần | Ý nghĩa |
|---|---|
| `EXPOSE 8080` | Metadata mô tả cổng HTTP dự kiến của container; chưa publish cổng ra máy Windows |
| `python -m uvicorn` | Chạy ASGI server bằng Python trong image |
| `app.main:app` | Import module `app/main.py` rồi lấy đối tượng FastAPI tên `app` |
| `--host 0.0.0.0` | Lắng nghe trên các interface mạng bên trong container để có thể nhận kết nối từ bên ngoài container |
| `--port 8080` | Chọn cổng mà Uvicorn lắng nghe bên trong container |

`CMD` đặt lệnh mặc định khi tạo container từ image. Dạng JSON ở đây chạy trực tiếp Python, không đi qua shell trung gian. `CMD` không khởi động web trong lúc build; các chỉ thị `RUN` mới thực thi ở build time.

Ở giai đoạn 1, web bind `127.0.0.1` trên máy Windows. Bên trong container, `127.0.0.1` chỉ là loopback của chính container; vì vậy server cần bind `0.0.0.0` để nhận kết nối qua mạng container. Địa chỉ và cổng publish phía Windows sẽ được chọn ở bước chạy container.

Dockerfile đầy đủ tới bước này:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY database/ ./database/

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home appuser

USER appuser

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Kiểm tra nội dung đã lưu:

```bash
cat Dockerfile
```

Tới đây Dockerfile đã có các phần cần thiết cho lần build đầu tiên. Build thành công, quyền đọc source của non-root user, HTTP endpoints và kết nối PostgreSQL chưa được xác nhận; chúng được kiểm tra trong các bước thực hành tiếp theo.

## 10. Build application image lần đầu

Trong Git Bash, tại thư mục gốc repository:

```bash
cd /d/multi-cloud-failover
docker build --platform linux/amd64 -t multi-cloud-failover:local .
```

| Tham số | Ý nghĩa |
|---|---|
| `--platform linux/amd64` | Chọn image Linux cho kiến trúc x86-64, phù hợp mục tiêu triển khai của project |
| `-t multi-cloud-failover:local` | Đặt tên image là `multi-cloud-failover`, tag là `local` |
| `.` | Dùng thư mục hiện tại làm build context; `.dockerignore` lọc file trong context này |

Lần đầu Docker cần tải base image và cài package nên có thể lâu hơn các lần build sau. Theo dõi log để xác định từng bước đọc Dockerfile, nạp context, cài dependency, sao chép source và tạo user.

Sau khi lệnh build kết thúc thành công, kiểm tra image được lưu trên máy:

```bash
docker image ls multi-cloud-failover:local
docker image inspect multi-cloud-failover:local --format '{{.Os}}/{{.Architecture}} user={{.Config.User}}'
```

Lệnh inspect cần trả về:

```text
linux/amd64 user=appuser
```

Nếu build lỗi, xử lý lỗi trước khi chạy hai lệnh kiểm tra; một tag có sẵn từ lần build cũ không chứng minh lần build hiện tại đã thành công. Khi cần xem log đầy đủ, chạy lại lệnh build với tùy chọn `--progress=plain`.

Build chỉ tạo image trong Docker image store local; chưa chạy web hoặc thay đổi topology database, chưa đẩy image lên registry hay triển khai lên cloud. Bước tiếp theo sẽ chạy container từ image và kiểm tra HTTP endpoints.

## 11. Chạy container và kiểm tra HTTP

Sau khi build thành công và image inspect đúng nền tảng/user, chạy trong Git Bash:

```bash
docker run -d --name mcf-web-smoke \
  -p 127.0.0.1:8280:8080 \
  -e APP_ENV=docker-smoke \
  -e APP_REGION=local-container \
  multi-cloud-failover:local
```

| Thành phần | Ý nghĩa |
|---|---|
| `-d` | Chạy container nền và trả lại terminal |
| `--name mcf-web-smoke` | Đặt tên để kiểm tra trạng thái/log và quản lý container |
| `-p 127.0.0.1:8280:8080` | Publish cổng 8080 trong container thành cổng 8280 trên loopback của Windows |
| `-e APP_ENV=...`, `-e APP_REGION=...` | Truyền identity khi chạy, không cần build lại image |
| `multi-cloud-failover:local` | Image dùng để tạo container; lệnh mặc định lấy từ `CMD` |

Cổng 8280 được chọn riêng với các cổng lab giai đoạn 1. Cần đảm bảo cổng này chưa bị chiếm. Dấu `\` trong lệnh Bash phải là ký tự cuối dòng, không thêm khoảng trắng phía sau.

Lệnh run trả về container ID chưa chứng minh ứng dụng đã khởi động thành công. Kiểm tra container và HTTP endpoints:

```bash
docker ps --filter name=mcf-web-smoke
curl -fsS http://127.0.0.1:8280/health/live
curl -fsS http://127.0.0.1:8280/version
```

Kết quả cần có:

- Container có trạng thái `Up` và mapping cổng `127.0.0.1:8280->8080/tcp`.
- `/health/live` trả HTTP 200 với JSON `{"status":"alive"}`.
- `/version` trả `environment=docker-smoke`, `region=local-container` và thông tin phiên bản.

`commit_sha` có thể là `not-built` vì image chưa được truyền commit và không chứa `.git`. Thông tin commit cho image phát hành sẽ được bổ sung ở bước cấu hình phiên bản/CI.

Mở trình duyệt tại [http://127.0.0.1:8280/issues.html](http://127.0.0.1:8280/issues.html) để kiểm tra static UI được phục vụ.

Container này chưa nhận `DATABASE_URL` hoặc tham gia mạng database của lab. Các API truy cập database chưa phải tiêu chí đạt của bước HTTP; giao diện có thể báo không kết nối database và `/api/database/status` có thể trả 503. Không dùng kết quả đó để kết luận Uvicorn chưa chạy. Bước tiếp theo cấu hình kết nối PostgreSQL trước khi thử tạo issue.

Nếu curl chưa kết nối được, xem log:

```bash
docker logs mcf-web-smoke
```

Nếu container đã thoát, xem trạng thái và log trước khi thử lại:

```bash
docker ps -a --filter name=mcf-web-smoke
docker logs mcf-web-smoke
```

Nếu tên container đã tồn tại, kiểm tra container đó thay vì chạy lại cùng lệnh run. Khi kết thúc bài HTTP, có thể dừng và xóa đúng container thử này; hai lệnh dưới không xóa image hoặc volume PostgreSQL:

```bash
docker stop mcf-web-smoke
docker rm mcf-web-smoke
```

## 12. Kiểm tra PostgreSQL trước khi kết nối container web

HTTP liveness và version không kiểm tra database. Trước khi thêm `DATABASE_URL`, xác nhận các container PostgreSQL của giai đoạn 1 đang hoạt động:

```bash
docker ps -a --filter label=com.docker.compose.project=mcf-todicode
```

Nếu cả hai container đang dừng do tắt Docker/máy và topology trước khi dừng vẫn là AWS primary, Azure standby ở trạng thái ổn định, khởi động lại các container đã tồn tại:

```bash
docker start mcf-todicode-database-1
docker start mcf-todicode-database-azure-1
```

`docker start` dùng lại cấu hình và volume của container, không tạo database mới. Nếu lab đã failover hoặc đang phục hồi dở, thực hiện [runbook recovery](../DISASTER_RECOVERY.md) thay vì tự khởi động primary cũ. Nếu container không tồn tại, quay lại bước khởi tạo ở giai đoạn 1.

Chờ PostgreSQL khởi động và kiểm tra:

```bash
docker ps --filter label=com.docker.compose.project=mcf-todicode
```

Cần thấy hai container ở trạng thái `Up` và healthcheck chuyển sang `healthy`.

Kiểm tra vai trò thực tế bằng SQL, chạy từ thư mục gốc repository trong Git Bash:

```bash
docker compose -p mcf-todicode -f database/compose.replication.yml exec -T database psql -U taskflow -d taskflow -c "SELECT pg_is_in_recovery() AS is_standby;"
docker compose -p mcf-todicode -f database/compose.replication.yml exec -T database-azure psql -U taskflow -d taskflow -c "SELECT pg_is_in_recovery() AS is_standby; SELECT status, sender_host FROM pg_stat_wal_receiver;"
```

Với topology ban đầu, AWS trả `is_standby=f`; Azure trả `is_standby=t` và receiver có `status=streaming`, `sender_host=database`. Nếu không đúng, xử lý topology/replication trước khi kiểm tra thao tác ghi từ container web.

Khi cần chẩn đoán khởi động, xem log đúng container:

```bash
docker logs --tail 50 mcf-todicode-database-1
docker logs --tail 50 mcf-todicode-database-azure-1
```

Database và container web sẽ cần cùng Docker network. Trong lab này, địa chỉ PostgreSQL dùng giữa các container là tên service và cổng nội bộ, ví dụ `database:5432`; cổng publish `56432` dành cho kết nối từ Windows. `127.0.0.1` bên trong container web chỉ trỏ về chính container web. Bước tiếp theo sẽ tạo cấu hình runtime và gắn web vào network `mcf-todicode_default`.

## 13. Chuẩn bị cấu hình runtime cho web AWS

Sau khi xác nhận AWS là primary và Azure là standby streaming, tự tạo file `.env.aws.local` tại thư mục gốc repository bằng trình soạn thảo hoặc Git Bash:

```bash
touch .env.aws.local
```

Nhập nội dung sau, không thêm dấu nháy quanh giá trị:

```dotenv
APP_ENV=aws
APP_REGION=local-container
DATABASE_URL=postgresql://taskflow:local-demo-only@database:5432/taskflow
```

| Biến | Vai trò |
|---|---|
| `APP_ENV` | Nhãn môi trường mà ứng dụng trả về trong identity và response header |
| `APP_REGION` | Nhãn vị trí triển khai; `local-container` cho biết đây vẫn là mô phỏng local |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL mà mã trong `database/connection.py` đọc khi mở kết nối |

Cấu trúc URL:

```text
postgresql://user:password@host:port/database_name
```

Trong cấu hình lab này:

- User ứng dụng là `taskflow`, mật khẩu demo là `local-demo-only`.
- Host `database` là tên service của PostgreSQL AWS trên network `mcf-todicode_default`.
- Port `5432` là cổng PostgreSQL bên trong container.
- Tên database là `taskflow`.

Không dùng `127.0.0.1:56432` cho kết nối trực tiếp giữa các container: cổng đó dành cho chương trình chạy trên Windows. Container web cần tham gia cùng network để phân giải tên `database`. Mật khẩu trong mục này chỉ là credential của lab local.

File `.env.aws.local` sẽ được truyền qua `docker run --env-file .env.aws.local`. Chỉ tạo file chưa cập nhật môi trường của container `mcf-web-smoke` đang chạy; không dùng `source` và không cần build lại image vì các giá trị này là cấu hình runtime.

Kiểm tra file đã được Git bỏ qua:

```bash
git check-ignore -v .env.aws.local
```

Kết quả cần trỏ tới quy tắc `.env.*` trong `.gitignore`. `.dockerignore` cũng đã có `.env.*`, nên file cấu hình không thuộc build context. Giữ file trên máy local; tài liệu này cung cấp nội dung mẫu để tái tạo.

Bước tiếp theo sẽ chạy container web với `--env-file` và `--network mcf-todicode_default`, rồi xác nhận kết nối database qua HTTP.

## 14. Chạy container web AWS có kết nối PostgreSQL

Điều kiện: `.env.aws.local` đã có nội dung ở mục 13, primary/standby đã được kiểm tra đúng vai trò, hai database đang chạy và network `mcf-todicode_default` tồn tại.

Container thử HTTP đang dùng cổng 8280. Nếu `mcf-web-smoke` còn tồn tại, dừng và xóa đúng container thử để dùng lại cổng này:

```bash
docker stop mcf-web-smoke
docker rm mcf-web-smoke
```

Hai lệnh không xóa application image và không tác động tới các container/volume PostgreSQL. Nếu container thử đã được xóa ở mục 11 thì bỏ qua hai lệnh này.

Tạo container web AWS từ cùng image đã build, trong Git Bash tại thư mục gốc repository:

```bash
docker run -d --name mcf-app-aws \
  --network mcf-todicode_default \
  --env-file .env.aws.local \
  -p 127.0.0.1:8280:8080 \
  multi-cloud-failover:local
```

Hai tùy chọn mới:

- `--network mcf-todicode_default`: cho web tham gia network của hai PostgreSQL. Docker DNS trên network này phân giải service name `database` tới container PostgreSQL AWS.
- `--env-file .env.aws.local`: đọc các giá trị runtime từ file và đặt vào môi trường container mới. File không được copy vào image và không được ứng dụng tự đọc trực tiếp.

Luồng kết nối:

```text
Windows/browser :8280 → mcf-app-aws :8080 → database :5432
                         cùng network mcf-todicode_default
```

Không cần build lại image khi thay cấu hình runtime. Nếu chỉnh `.env.aws.local` sau khi container được tạo, cần tạo lại container với file đã sửa; restart container cũ không tự đọc lại file trên Windows.

Kiểm tra:

```bash
docker ps --filter name=mcf-app-aws
curl -fsS http://127.0.0.1:8280/health/live
curl -fsS http://127.0.0.1:8280/api/database/status
```

Với topology AWS primary đang mở gate ghi, status cần trả HTTP 200 và có `connected=true`, `role=primary`, `writable=true`. `current_lsn` là vị trí WAL hiện tại, thay đổi theo hoạt động database.

Có thể kiểm tra thêm writer readiness và identity:

```bash
curl -i -sS http://127.0.0.1:8280/health/database
curl -fsS http://127.0.0.1:8280/version
```

Writer readiness cần trả HTTP 200; version cần thể hiện `environment=aws`, `region=local-container`. Readiness kiểm tra kết nối/role/gate ghi, chưa thay thế bài kiểm tra tạo issue thực tế.

Mở [http://127.0.0.1:8280/issues.html](http://127.0.0.1:8280/issues.html). Sau khi database status đúng, giao diện phải đọc được dữ liệu lab đã có. Dữ liệu vẫn nằm trong volume PostgreSQL của giai đoạn 1.

Nếu chưa kết nối HTTP được ngay sau `docker run`, chờ ứng dụng khởi động rồi thử lại. Nếu lỗi tiếp tục, xem log và danh sách container trong network:

```bash
docker logs --tail 50 mcf-app-aws
docker network inspect mcf-todicode_default --format '{{range .Containers}}{{println .Name}}{{end}}'
```

Cần thấy container web và hai container database trong network. Khi lỗi kết nối PostgreSQL, kiểm tra DB đang chạy, host `database`, port `5432` và credential lab trong `.env.aws.local`.

## 15. Chạy container web Azure kết nối standby

Sử dụng cùng image `multi-cloud-failover:local` như web AWS. Tự tạo file `.env.azure.local` tại thư mục gốc repository:

```bash
touch .env.azure.local
```

Nhập nội dung:

```dotenv
APP_ENV=azure
APP_REGION=local-container
DATABASE_URL=postgresql://taskflow:local-demo-only@database-azure:5432/taskflow
```

So với cấu hình AWS, đổi `APP_ENV` thành `azure` và host PostgreSQL thành `database-azure`. Standby được sao chép vật lý từ primary nên tài khoản ứng dụng và tên database vẫn là `taskflow`. Không dùng mật khẩu replication cho kết nối ứng dụng.

Kiểm tra hai file runtime được Git bỏ qua:

```bash
git check-ignore -v .env.aws.local .env.azure.local
```

Chạy container web Azure trong cùng network, publish cổng 8281 trên Windows để không trùng web AWS:

```bash
docker run -d --name mcf-app-azure \
  --network mcf-todicode_default \
  --env-file .env.azure.local \
  -p 127.0.0.1:8281:8080 \
  multi-cloud-failover:local
```

Hai web cùng lắng nghe cổng 8080 bên trong hai container riêng. Cổng phía Windows khác nhau: AWS dùng 8280, Azure dùng 8281. Việc đổi identity và database không yêu cầu build thêm image.

Kiểm tra sau khi ứng dụng khởi động:

```bash
docker ps --filter name=mcf-app-
curl -fsS http://127.0.0.1:8281/health/live
curl -fsS http://127.0.0.1:8281/version
curl -fsS http://127.0.0.1:8281/api/database/status
```

Với topology ban đầu:

| Endpoint/field | Kết quả cần có |
|---|---|
| `/health/live` | HTTP 200, `status=alive` |
| `/version` | `environment=azure`, `region=local-container` |
| Database status | HTTP 200, `connected=true`, `role=standby`, `writable=false`, `replication_connected=true` |

`receive_lsn` và `replay_lsn` cho biết vị trí WAL đã nhận và đã replay. Chúng có thể thay đổi giữa các lần đọc.

Phân biệt database status với writer readiness:

```bash
curl -i -sS http://127.0.0.1:8281/health/database
```

Endpoint writer readiness cần trả HTTP 503 khi Azure còn là standby. Đây là trạng thái đúng: web vẫn chạy và đọc được database, nhưng chưa được dùng làm writer. Endpoint `/api/database/status` vẫn trả HTTP 200 khi đọc được trạng thái standby.

Mở [web AWS](http://127.0.0.1:8280/issues.html) và [web Azure](http://127.0.0.1:8281/issues.html). Hai web dùng cùng ứng dụng và hai database riêng, dữ liệu đồng bộ qua WAL. Bước tiếp theo sẽ tạo dữ liệu qua web AWS và kiểm tra cùng dữ liệu qua web Azure.

Nếu container không khởi động hoặc status lỗi:

```bash
docker logs --tail 50 mcf-app-azure
```

Kiểm tra network, host `database-azure`, thông tin đăng nhập và trạng thái PostgreSQL trước khi chạy lại. Nếu container tên `mcf-app-azure` đã tồn tại, xem trạng thái/log của nó trước khi tạo container cùng tên.

## 16. Kiểm tra dữ liệu qua hai container web

Hai web phải kết nối đúng vai trò ở các mục trước. Bài này xác nhận image chạy được nghiệp vụ có database, không chỉ trả về liveness.

### 16.1. Xác nhận cùng application image

```bash
docker inspect mcf-app-aws mcf-app-azure --format '{{.Name}} image={{.Image}} user={{.Config.User}}'
```

Hai dòng cần có cùng image ID và `user=appuser`. Image ID giống nhau chứng minh hai container dùng cùng nội dung image, ngay cả khi tag có thể được gán lại sau lần build khác.

### 16.2. Tạo issue trên AWS và đọc trên Azure

1. Mở [web AWS](http://127.0.0.1:8280/issues.html), chọn tạo issue.
2. Nhập tên người gửi, tiêu đề `Docker replication 01`, mô tả `Tao tu container web AWS de kiem tra WAL replication` và trạng thái Open.
3. Lưu, ghi lại số issue hiển thị để đối chiếu. Nếu chạy lại bài kiểm tra, dùng tiêu đề có số thứ tự mới để phân biệt lượt.
4. Mở [web Azure](http://127.0.0.1:8281/issues.html), dùng nút Làm mới nếu cần và tìm issue vừa tạo.
5. Đối chiếu số issue, tiêu đề, mô tả, người tạo và trạng thái giữa hai web.

Nếu chưa thấy dữ liệu ngay, chờ và làm mới vì replication bất đồng bộ và giao diện có chu kỳ polling riêng. Nếu lỗi kéo dài, kiểm tra receiver/replay và log thay vì đổi vai trò database để xử lý độ trễ.

### 16.3. Kiểm tra thay đổi tiếp theo

1. Trên AWS, mở issue vừa tạo và gửi bình luận `Binh luan tu container AWS`.
2. Trên Azure, làm mới chi tiết issue và xác nhận bình luận cùng sự kiện lịch sử xuất hiện.
3. Các thao tác ghi thực hiện trên AWS; Azure tiếp tục là standby chỉ đọc.

Luồng dữ liệu cần giải thích được:

```text
Trình duyệt → web AWS container → PostgreSQL primary
                                     ↓ WAL streaming/replay
Trình duyệt ← web Azure container ← PostgreSQL standby
```

Việc hai web đọc được cùng issue và bình luận xác nhận dữ liệu nghiệp vụ đã đi qua hai kết nối database và luồng replication. WAL LSN thay đổi một mình chưa chứng minh đúng nội dung nghiệp vụ.

### 16.4. Điều kiện kết thúc bài kiểm tra

- Hai container web dùng cùng image và chạy bằng `appuser`.
- AWS status là primary, writable; Azure status là standby, read-only và receiver streaming.
- Issue tạo qua web AWS xuất hiện với cùng số issue và nội dung trên web Azure.
- Bình luận và lịch sử tương ứng xuất hiện trên cả hai bên.
- Hai file cấu hình runtime vẫn được Git bỏ qua.

Chỉ đánh dấu giai đoạn Docker hóa hoàn thành khi đã chạy và xác nhận các bước này. Bài kiểm tra vẫn diễn ra trên một máy local; chưa chứng minh khả năng chịu lỗi độc lập của AWS/Azure thật.

## 17. Theo dõi tiến độ

Nghiệm thu local đã xác nhận build Linux AMD64, hai web cùng image ID chạy bằng `appuser`, kết nối primary/standby và bài kiểm tra issue/bình luận qua hai web.

- [x] Kiểm tra Docker Engine và chế độ Linux containers.
- [x] Tạo và hiểu nền tảng Dockerfile.
- [x] Chuẩn bị build context và `.dockerignore`.
- [x] Cài runtime dependency và sao chép source vào image.
- [x] Cấu hình user chạy ứng dụng và lệnh khởi động.
- [x] Build image và kiểm tra giao diện, identity, health endpoints.
- [x] Kết nối ứng dụng container với PostgreSQL local và kiểm tra dữ liệu.

Khi tái tạo project trên máy khác, thực hiện lại các phép kiểm tra thay vì suy ra kết quả từ checklist. Phạm vi nghiệm thu là local; image chưa được phát hành lên registry và chưa triển khai cloud.

Tiếp theo: [Giai đoạn 3 — CI và container registry](giaidoan3_ci_va_container_registry.md).
