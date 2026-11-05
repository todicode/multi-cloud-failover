# Giai đoạn 3 — CI và container registry

## 1. Mục tiêu và đầu ra

Tự động kiểm thử và đóng gói ứng dụng bằng GitHub Actions, phát hành application image lên GitHub Container Registry (GHCR), sau đó kéo lại image theo digest để kiểm tra khả năng phân phối.

Tham chiếu bước chuẩn bị: [Giai đoạn 2 — Docker hóa ứng dụng](giaidoan2_docker_hoa_ungdung.md).

Tài liệu được bổ sung theo từng bước. Hiện tại đã hướng dẫn job kiểm thử API/database với Python 3.12, PostgreSQL 17 và cách push để kiểm chứng trên GitHub. Job chưa được xác nhận chạy thành công; các phần build/publish image và kiểm tra pull theo digest sẽ được bổ sung sau.

Điều kiện nghiệm thu khi kết thúc toàn bộ giai đoạn:

- Workflow chạy kiểm thử API/database với PostgreSQL riêng của CI.
- Build application image cho Linux AMD64 sau khi kiểm thử đạt.
- Phát hành image lên GHCR từ sự kiện được cho phép; pull request chỉ kiểm thử/build.
- Ghi nhận commit và digest của image đã phát hành.
- Kéo image bằng digest trong môi trường kiểm tra riêng và xác nhận HTTP/runtime identity.
- Có lượt chạy GitHub Actions thành công để làm bằng chứng.

Hạ tầng AWS/Azure và triển khai workload được thực hiện ở các giai đoạn sau. CI dùng môi trường runner của GitHub, không kết nối database local trên máy Windows.

## 2. Các khái niệm sử dụng

| Khái niệm | Vai trò trong project |
|---|---|
| GitHub Actions | Dịch vụ thực thi các công việc tự động dựa trên sự kiện của repository |
| Workflow | File YAML mô tả khi nào chạy, chạy công việc nào và dùng quyền gì |
| Job | Nhóm bước chạy trên một runner; có thể phụ thuộc kết quả job khác |
| Runner | Máy thực thi job, sẽ dùng Linux cho kiểm thử và build image |
| GHCR | Registry lưu image để các máy khác có thể pull |
| Digest | Định danh nội dung image dùng khi chọn bản triển khai cụ thể |

Luồng mục tiêu:

```text
Push / pull request → Test với PostgreSQL → Build image
                                               ↓ Sự kiện phát hành hợp lệ
                                       Push GHCR và lưu digest
                                               ↓
                                      Pull lại và kiểm tra runtime
```

## 3. Tạo file workflow và khai báo sự kiện

Trong Git Bash tại thư mục gốc repository:

```bash
cd /d/multi-cloud-failover
mkdir -p .github/workflows
touch .github/workflows/container.yml
```

Mở `.github/workflows/container.yml`, nhập phần đầu:

```yaml
name: Test and publish container

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read
```

| Cấu hình | Ý nghĩa |
|---|---|
| `name` | Tên hiển thị trong tab Actions của repository |
| `on.push.branches` | Kích hoạt khi có commit được push vào `main` |
| `on.pull_request.branches` | Kích hoạt theo các sự kiện pull request mặc định khi nhánh đích là `main` |
| `permissions.contents: read` | Cấp quyền đọc nội dung repository cho token tạm của workflow |

Ở pull request, `branches: [main]` lọc nhánh đích, không phải tên nhánh đang phát triển. YAML cần thụt lề bằng khoảng trắng theo đúng cấu trúc mẫu.

Đây mới là phần đầu của file. GitHub Actions yêu cầu workflow có job; hoàn thiện phần `jobs` ở bước tiếp theo trước khi commit/push workflow. Chưa chạy hoặc phát hành image từ đoạn khai báo này.

Kiểm tra nội dung đã nhập:

```bash
cat .github/workflows/container.yml
```

## 4. Tạo job Linux và lấy source

Thêm đoạn sau vào cuối `.github/workflows/container.yml`, sau phần `permissions`:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - name: Check out source
        uses: actions/checkout@v7
```

| Cấu hình | Ý nghĩa |
|---|---|
| `jobs` | Nhóm các job của workflow, cùng cấp với `name`, `on` và `permissions` |
| `test` | ID do project đặt cho job kiểm thử; các job sau có thể tham chiếu ID này |
| `runs-on: ubuntu-latest` | Dùng runner Ubuntu do GitHub cung cấp để thực thi job |
| `steps` | Danh sách các bước thực hiện theo thứ tự trên runner của job |
| `name: Check out source` | Nhãn hiển thị của bước, có thể đặt tên khác |
| `uses: actions/checkout@v7` | Sử dụng action checkout phiên bản major 7 để lấy repository vào workspace của runner |

Runner mới chưa có source của project chỉ vì workflow nằm trong repository. Checkout đưa source tương ứng với sự kiện workflow vào workspace để các lệnh sau đọc được `requirements-dev.txt`, `tests/` và Dockerfile. Quyền `contents: read` ở phần trước cho phép đọc repository.

Job chạy trên môi trường Linux của GitHub, không chạy trên Windows hay sử dụng Docker network của lab. Khi cấu hình PostgreSQL cho CI, database đó cũng được tạo riêng trong job.

Workflow tới bước này:

```yaml
name: Test and publish container

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - name: Check out source
        uses: actions/checkout@v7
```

Kiểm tra nội dung đã lưu:

```bash
cat .github/workflows/container.yml
```

Tới đây workflow chỉ có một bước lấy source. Job tên `test` chưa chạy kiểm thử; kết quả checkout thành công chưa chứng minh ứng dụng đạt. Hoàn thiện Python, PostgreSQL và lệnh test trước lượt push kiểm chứng CI. Bước tiếp theo chuẩn bị Python runtime và dependency.

## 5. Chuẩn bị Python và thư viện kiểm thử

Trong `.github/workflows/container.yml`, thêm hai bước sau dưới bước checkout. Mỗi dòng `- name` mới cùng mức thụt lề với `- name: Check out source`:

```yaml
      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - name: Install test dependencies
        run: python -m pip install -r requirements-dev.txt
```

`actions/setup-python@v7` chuẩn bị Python và thêm vào PATH của runner. `with` truyền tham số cho action; `python-version: "3.12"` chọn Python 3.12 để thống nhất với môi trường phát triển và application image.

`run` thực hiện lệnh shell trên runner, trong workspace đã có source từ bước checkout. `python -m pip` gọi pip bằng Python vừa được chuẩn bị.

Phân biệt hai file requirements:

| File | Cách sử dụng |
|---|---|
| `requirements.txt` | Dependency chạy ứng dụng, được cài khi build application image |
| `requirements-dev.txt` | Bao gồm runtime dependency qua dòng `-r requirements.txt` và công cụ kiểm thử như pytest; dùng trong job test |

Không sao chép `.venv` trên Windows vào CI. Runner cài dependency riêng từ các file được commit trong repository.

Danh sách `steps` sau bước này:

```yaml
    steps:
      - name: Check out source
        uses: actions/checkout@v7

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - name: Install test dependencies
        run: python -m pip install -r requirements-dev.txt
```

Kiểm tra file đã lưu:

```bash
cat .github/workflows/container.yml
```

Các bước trên mới mô tả việc chuẩn bị môi trường, chưa chạy test và chưa được xác nhận trên GitHub. Phần tiếp theo cấu hình PostgreSQL service riêng cho CI và bật các bài kiểm thử database trước khi thêm lệnh pytest.

## 6. Tạo PostgreSQL service cho job test

Các bài test trong `tests/test_issues.py` cần PostgreSQL thật. GitHub runner tạo database riêng cho CI, không kết nối container hoặc volume của lab local.

Trong `.github/workflows/container.yml`, thêm khối sau ngay dưới `runs-on: ubuntu-latest` và trước `steps:`. `services` cùng cấp thụt lề với `runs-on` và `steps`:

```yaml
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_USER: taskflow
          POSTGRES_PASSWORD: local-demo-only
          POSTGRES_DB: taskflow
        ports:
          - "55432:5432"
        options: >-
          --health-cmd "pg_isready -U taskflow -d taskflow"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
```

| Thành phần | Vai trò |
|---|---|
| `services.postgres` | Khai báo service container tên `postgres` phục vụ job |
| `image: postgres:17` | Khởi tạo PostgreSQL cùng major version với database của project |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Khởi tạo tài khoản và database dùng cho lượt kiểm thử |
| `ports: "55432:5432"` | Map cổng 55432 trên runner tới cổng 5432 trong service container |
| `options: >-` | Gộp các dòng cấu hình Docker options thành một chuỗi |
| `pg_isready` | Healthcheck xác nhận PostgreSQL đã nhận kết nối trước khi thực hiện các bước của job |

`--health-interval` là chu kỳ kiểm tra, `--health-timeout` là thời gian tối đa mỗi lần kiểm tra, `--health-retries` là ngưỡng lỗi để đánh dấu unhealthy. GitHub chuẩn bị service container trước các steps và dọn container khi job kết thúc.

Vì job hiện chạy Python trực tiếp trên runner Ubuntu, đường kết nối cho test là:

```text
Python/pytest trên runner → 127.0.0.1:55432 → PostgreSQL service :5432
```

Host dùng cho test sẽ là `127.0.0.1`, khác với `database:5432` của web container trong lab local. Nếu một job được cấu hình chạy trong job container thì cách dùng tên service/cổng nội bộ sẽ khác; job hiện tại không có cấu hình đó.

Thông tin đăng nhập trên chỉ dành cho database kiểm thử được tạo theo job. Giống tên/mật khẩu lab không đồng nghĩa dùng chung database. Các bài test tự tạo schema riêng và bootstrap bảng trong schema đó; không cần copy dữ liệu issue local sang CI.

Kiểm tra vị trí các khối sau khi lưu:

```bash
cat .github/workflows/container.yml
```

Tới đây mới khai báo service. Bước tiếp theo sẽ đặt `DATABASE_URL`, bật `TASKFLOW_DB_TESTS=1` và thêm lệnh pytest để thực sự chạy các bài kiểm thử database.

## 7. Cấu hình kết nối và chạy pytest

### 7.1. Đặt biến môi trường cho job

Thêm khối sau bên trong job `test`, sau phần `services` và trước `steps`. `env` ở đây cùng cấp với `runs-on`, `services` và `steps`:

```yaml
    env:
      TASKFLOW_DB_TESTS: "1"
      DATABASE_URL: postgresql://taskflow:local-demo-only@127.0.0.1:55432/taskflow
```

`DATABASE_URL` trỏ tới cổng đã publish của PostgreSQL service trên runner. Các giá trị user/password/database phải khớp với `services.postgres.env`.

`TASKFLOW_DB_TESTS` là cờ do project quy định, không phải biến đặc biệt của GitHub hoặc PostgreSQL. Trong `tests/test_issues.py`, các bài integration test chỉ chạy khi biến này đúng bằng chuỗi `"1"`; nếu thiếu, pytest bỏ qua các bài đó. Vì vậy một lượt pytest thành công nhưng có test database bị skip chưa xác nhận được kết nối CI.

Phân biệt hai phạm vi `env`:

- `services.postgres.env`: biến bên trong container PostgreSQL để khởi tạo DB.
- `jobs.test.env`: biến cho các bước chạy trên runner, gồm Python/pytest và mã ứng dụng được test.

### 7.2. Thêm bước chạy test

Thêm dưới bước `Install test dependencies`, cùng mức thụt lề với các dòng `- name` trước đó:

```yaml
      - name: Run API and database tests
        run: python -m pytest -q
```

`python -m pytest` chạy bộ kiểm thử; `-q` rút gọn output. File `pytest.ini` đã giới hạn `testpaths = tests`, cấu hình Python import path và tắt cache provider. Không cần khởi động Uvicorn riêng: các test API sử dụng FastAPI TestClient.

Job tạo PostgreSQL service, chờ healthcheck, lấy source, chuẩn bị Python, cài dependency rồi chạy test. Các test database tự tạo schema riêng và dọn schema khi kết thúc.

### 7.3. Workflow đầy đủ cho lượt kiểm thử đầu tiên

Đối chiếu file đã nhập với nội dung sau:

```yaml
name: Test and publish container

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_USER: taskflow
          POSTGRES_PASSWORD: local-demo-only
          POSTGRES_DB: taskflow
        ports:
          - "55432:5432"
        options: >-
          --health-cmd "pg_isready -U taskflow -d taskflow"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    env:
      TASKFLOW_DB_TESTS: "1"
      DATABASE_URL: postgresql://taskflow:local-demo-only@127.0.0.1:55432/taskflow

    steps:
      - name: Check out source
        uses: actions/checkout@v7

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - name: Install test dependencies
        run: python -m pip install -r requirements-dev.txt

      - name: Run API and database tests
        run: python -m pytest -q
```

Kiểm tra nội dung đã lưu:

```bash
cat .github/workflows/container.yml
```

Lượt chạy thành công cần có step pytest thực sự chạy và các test database không bị skip. Bộ test hiện tại gồm 19 test; chỉ ghi nhận kết quả CI sau khi xem log trên GitHub. Workflow lúc này mới kiểm thử, chưa build hoặc phát hành container dù tên workflow đã mô tả mục tiêu cuối.

Bước tiếp theo sẽ kiểm tra file đã viết, hướng dẫn commit theo Conventional Commits, push lên GitHub và đọc kết quả Actions. Các lệnh Git cho lượt chạy đầu tiên sẽ được bổ sung ở bước đó.

## 8. Commit và chạy job kiểm thử lần đầu

Trước khi commit, kiểm tra YAML đúng cấu trúc mục 7.3 và xóa khoảng trắng thừa ở cuối dòng, kể cả các dòng trống. Workflow ở bước này chỉ chạy kiểm thử; chưa phát hành image.

Kiểm tra trạng thái Git và các file cấu hình được bỏ qua:

```bash
git status --short
git check-ignore -v .env.aws.local .env.azure.local
```

Hai file runtime cần khớp quy tắc `.env.*`. Các file `.dockerignore`, Dockerfile, workflow và tài liệu hướng dẫn cần được commit để người khác có thể tái tạo các bước.

### 8.1. Lưu phần Docker hóa

Nếu các thay đổi giai đoạn 2 chưa được commit, chạy từ thư mục gốc repository:

```bash
git add -- Dockerfile .dockerignore README.md docs/ROADMAP.md docs/instruction/giaidoan2_docker_hoa_ungdung.md
git diff --cached --check
git commit -m "feat(docker): package application for local replication lab"
```

Chỉ chạy commit sau khi `git diff --cached --check` không báo lỗi. Nếu có lỗi whitespace, sửa file, chạy lại `git add` cho file đó rồi kiểm tra lại. Nếu giai đoạn 2 đã được commit trước đó, bỏ qua nhóm lệnh này.

### 8.2. Lưu workflow và hướng dẫn CI

```bash
git add -- .github/workflows/container.yml docs/instruction/giaidoan3_ci_va_container_registry.md
git diff --cached --check
git commit -m "ci: run API and PostgreSQL integration tests"
```

Hai thông điệp theo Conventional Commits: `feat(docker)` mô tả chức năng đóng gói ứng dụng; `ci` mô tả cấu hình kiểm thử tự động. Phạm vi file được thêm rõ ràng thay vì đưa toàn bộ working tree vào commit.

### 8.3. Push và đọc kết quả GitHub Actions

Sau khi cả hai phần đã được lưu thành commit và đang ở nhánh `main`:

```bash
git push origin main
```

GitHub nhận push sẽ kích hoạt workflow. Mở repository → tab Actions → workflow `Test and publish container` → lượt chạy tương ứng với commit vừa push → job `test`.

Kiểm tra các bước checkout, setup Python, install dependency và `Run API and database tests`. Trong log pytest cần có đủ các test database được chạy. Với bộ test hiện tại, kết quả mong đợi là `19 passed`; không ghi nhận đạt chỉ từ tên job hoặc việc khởi tạo service thành công.

Nếu job đỏ, mở step đầu tiên thất bại và đọc lỗi. Phân biệt lỗi tải action/package, PostgreSQL khởi động, kết nối database và assertion của test. Sửa đúng nguyên nhân, commit thay đổi rồi push để chạy lượt mới.

Nếu Git từ chối push do remote có commit mới, lấy và đối chiếu các thay đổi trước khi push lại; không dùng force push để bỏ qua lịch sử. Việc xác thực Git thực hiện bằng account đã cấu hình trên máy; không cần credential AWS/Azure để chạy job CI này.

Lưu link lượt chạy thành công cùng commit SHA làm bằng chứng kiểm thử. Chỉ phần job test được nghiệm thu ở bước này; tiếp theo mới bổ sung build image và phát hành GHCR.

## 9. Theo dõi tiến độ

- [ ] Tạo file và hiểu tên workflow, sự kiện kích hoạt, quyền đọc source.
- [ ] Bổ sung job Linux và checkout source.
- [ ] Chuẩn bị Python runtime và dependency.
- [ ] Cấu hình PostgreSQL service và chạy test.
- [ ] Cấu hình build image sau khi test đạt.
- [ ] Phát hành GHCR và lưu digest/commit.
- [ ] Pull image bằng digest và xác nhận runtime.
- [ ] Xác nhận lượt chạy GitHub Actions thành công.

Hướng dẫn cho các phần chưa thực hành sẽ được bổ sung theo tiến độ. Checklist không thay thế kết quả chạy workflow.
