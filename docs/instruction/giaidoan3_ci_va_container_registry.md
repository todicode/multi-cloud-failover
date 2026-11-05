# Giai đoạn 3 — CI và container registry

## 1. Mục tiêu và đầu ra

Tự động kiểm thử và đóng gói ứng dụng bằng GitHub Actions, phát hành application image lên GitHub Container Registry (GHCR), sau đó kéo lại image theo digest để kiểm tra khả năng phân phối.

Tham chiếu bước chuẩn bị: [Giai đoạn 2 — Docker hóa ứng dụng](giaidoan2_docker_hoa_ungdung.md).

Tài liệu được bổ sung theo từng bước. Kiểm thử API/database, build Linux AMD64 và publish GHCR đã chạy thành công trên GitHub Actions. Pull bằng digest và runtime/database đã được xác nhận local. Phần dưới hướng dẫn job output, pull trên runner riêng và HTTP smoke check; job kiểm tra độc lập vẫn cần hoàn thiện và chạy nghiệm thu.

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

## 9. Build image sau khi test đạt

Sau khi job `test` chạy thành công trên GitHub, bổ sung job `container` bên dưới job đó trong `.github/workflows/container.yml`:

```yaml
  container:
    needs: test
    runs-on: ubuntu-latest

    steps:
      - name: Check out source
        uses: actions/checkout@v7

      - name: Build application image
        run: docker build --platform linux/amd64 -t multi-cloud-failover:ci .
```

`container:` thụt lề hai khoảng trắng, cùng cấp với `test:` bên dưới `jobs:`. Không đặt nó bên trong `steps` của job test và không tạo thêm khóa `jobs` thứ hai.

| Thành phần | Ý nghĩa |
|---|---|
| `container` | ID của job đóng gói ứng dụng; tên này không có nghĩa job sử dụng cấu hình job container |
| `needs: test` | Chờ job `test` thành công; nếu test lỗi hoặc bị skip, job này cũng bị skip theo cấu hình mặc định |
| `runs-on: ubuntu-latest` | Thực hiện build trên runner Ubuntu của job này |
| Checkout | Lấy source vào workspace của runner mới |
| `docker build` | Build Dockerfile và context đã commit trong repository |
| `multi-cloud-failover:ci` | Tag image trong Docker image store của runner build |

Hai job GitHub-hosted sử dụng môi trường runner riêng. Source, thư viện Python và PostgreSQL của job `test` không tự chuyển sang job `container`, nên cần checkout lần nữa. Bước build không cần setup Python trên runner: Python và dependency ứng dụng được chuẩn bị bên trong image theo Dockerfile.

Luồng hiện tại:

```text
test: PostgreSQL → checkout → Python → dependency → pytest
                                                       ↓ Chỉ khi đạt
container: checkout → docker build Linux AMD64
```

Image `:ci` mới tồn tại trên runner build và chưa được phát hành. Khi runner được dọn, không thể pull image này từ máy cá nhân nếu chưa push lên registry. Tag này cũng không thay đổi image `:local` của lab trên Windows.

Kiểm tra nội dung đã lưu:

```bash
cat .github/workflows/container.yml
```

Phần tiếp theo kiểm tra cấu trúc file rồi commit/push để chạy cả hai job. Sau khi build trên CI đạt mới bổ sung đăng nhập và phát hành GHCR. Không cần thêm PostgreSQL service vào job build vì Dockerfile không kết nối database trong lúc build.

### 9.1. Commit và kiểm chứng job build

Sau khi kiểm tra YAML có hai job `test` và `container`, trong đó job `container` có `needs: test`, chạy từ thư mục gốc repository:

```bash
git add -- .github/workflows/container.yml README.md docs/ROADMAP.md docs/instruction/giaidoan3_ci_va_container_registry.md
git diff --cached --check
```

Khi kiểm tra không báo lỗi, lưu và push:

```bash
git commit -m "ci: build application image after tests pass"
git push origin main
```

Mở Actions và chọn lượt chạy mới. Job `test` cần thành công trước, sau đó job `container` mới chạy. Mở `container` → `Build application image` để xem log Docker build và xác nhận bước kết thúc thành công. Cả hai job cần xanh; trường hợp `container` bị skip vì test lỗi không được tính là build đạt.

Lượt chạy này xác nhận source đã commit có thể build image trên runner Linux độc lập với máy phát triển. Nó chưa kiểm tra khởi động image, chưa push GHCR và chưa triển khai AWS/Azure. Sau khi job build đạt, phần tiếp theo bổ sung phát hành image lên registry.

## 10. Chuẩn bị tên image và quyền phát hành GHCR

GHCR là GitHub Container Registry, registry lưu image tại `ghcr.io`. Sau khi image được phát hành, các máy khác có quyền truy cập có thể pull image thay vì tự build lại source.

### 10.1. Đặt tên image dùng trong workflow

Thêm khối sau ở cấp workflow, sau `permissions` và trước `jobs`:

```yaml
env:
  IMAGE_NAME: ghcr.io/${{ github.repository }}
```

`github.repository` là context do GitHub cung cấp, có dạng `owner/repository`. Với repository này, giá trị là `todicode/multi-cloud-failover`, nên `IMAGE_NAME` trở thành:

```text
ghcr.io/todicode/multi-cloud-failover
```

Đây là tên image, chưa có tag hoặc digest. `IMAGE_NAME` là tên biến do workflow quy định. Các job kế thừa biến cấp workflow; khi dùng trong lệnh shell trên runner có thể tham chiếu bằng `$IMAGE_NAME`.

Chỉ thêm một khối `env` ở cấp workflow. Giữ khối `env` bên trong job `test` cho `TASKFLOW_DB_TESTS` và `DATABASE_URL`; hai phạm vi này khác nhau.

### 10.2. Cấp quyền cho job container

Trong job `container`, thêm khối sau dưới `runs-on`, trước `steps`:

```yaml
    permissions:
      contents: read
      packages: write
```

`contents: read` cho phép checkout source. `packages: write` cho phép token của job phát hành package/image gắn với repository lên GHCR. Quyền này chỉ được khai báo cho job `container`; giữ quyền cấp workflow là `contents: read`.

GitHub tự cấp `GITHUB_TOKEN` cho workflow run. Khi bổ sung bước đăng nhập GHCR sẽ dùng token này; không cần tạo token cá nhân cho bước publish image của chính repository.

Khung job sau khi thêm quyền, với các bước hiện có được giữ nguyên:

```yaml
  container:
    needs: test
    runs-on: ubuntu-latest

    permissions:
      contents: read
      packages: write

    steps:
      - name: Check out source
        uses: actions/checkout@v7

      - name: Build application image
        run: docker build --platform linux/amd64 -t multi-cloud-failover:ci .
```

Ở bước này lệnh build vẫn dùng tag local trên runner `multi-cloud-failover:ci`. Thêm biến và quyền chưa đổi tên image đang build, chưa đăng nhập và chưa push lên GHCR. Bước tiếp theo sẽ thêm đăng nhập cùng điều kiện chỉ phát hành từ push vào nhánh `main`; pull request tiếp tục chỉ test/build.

Kiểm tra vị trí các khối:

```bash
cat .github/workflows/container.yml
```

Không cần tạo package GHCR thủ công trước bước này; package được tạo khi lần publish đầu tiên thành công. Hoàn thiện đăng nhập/tag/push trước lượt chạy kiểm chứng phần registry.

## 11. Đăng nhập GHCR trong job container

### 11.1. Kiểm tra phạm vi permissions

Trước khi thêm login, kiểm tra khối sau nằm trong `jobs.container`, không nằm trong `jobs.test`:

```yaml
    permissions:
      contents: read
      packages: write
```

Nếu đã đặt nhầm trong job `test`, chuyển nguyên khối sang job `container`, ngay dưới `runs-on` và trước `steps`. Job `test` dùng quyền đọc kế thừa từ workflow; job `container` cần quyền ghi package cho bước phát hành.

### 11.2. Thêm bước login

Trong danh sách `steps` của job `container`, thêm sau checkout và trước `Build application image`:

```yaml
      - name: Log in to GHCR
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```

| Cấu hình | Vai trò |
|---|---|
| `if` | Chỉ thực hiện login khi sự kiện là push và nhánh là `main` |
| `docker/login-action@v4` | Action đăng nhập Docker registry trên runner của job |
| `registry: ghcr.io` | Chọn GitHub Container Registry |
| `github.actor` | Tài khoản gắn với người hoặc ứng dụng kích hoạt workflow run |
| `secrets.GITHUB_TOKEN` | Token tự động của workflow run; không phải mật khẩu tài khoản GitHub |

Các biểu thức `${{ ... }}` được GitHub xử lý khi chuẩn bị workflow. Không thay chúng bằng token thật và không tạo secret thủ công tên `GITHUB_TOKEN`.

Điều kiện `if` ở đây chỉ áp dụng cho step login. Pull request vẫn thực hiện job test và build, nhưng bỏ qua login. Bước push image sau này cũng cần cùng điều kiện để chỉ phát hành từ push vào `main`.

Job `container` sau bước này:

```yaml
  container:
    needs: test
    runs-on: ubuntu-latest

    permissions:
      contents: read
      packages: write

    steps:
      - name: Check out source
        uses: actions/checkout@v7

      - name: Log in to GHCR
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build application image
        run: docker build --platform linux/amd64 -t multi-cloud-failover:ci .
```

Login chỉ xác thực Docker client trên runner với registry. Image vẫn dùng tag `multi-cloud-failover:ci` và chưa được push. Không cần chạy `docker login` trên Windows cho workflow; runner thực hiện việc đăng nhập riêng.

Kiểm tra file sau khi lưu:

```bash
cat .github/workflows/container.yml
```

Bước tiếp theo đổi tag của image sang tên GHCR và bổ sung push có điều kiện. Sau khi hoàn thiện các phần đó mới commit/push để kiểm chứng phát hành.

## 12. Đặt tag GHCR và push image

### 12.1. Đổi bước build

Trong job `container`, thay bước `Build application image` hiện tại bằng:

```yaml
      - name: Build application image
        run: |
          docker build --platform linux/amd64 \
            --label "org.opencontainers.image.source=https://github.com/${GITHUB_REPOSITORY}" \
            --label "org.opencontainers.image.revision=${GITHUB_SHA}" \
            -t "${IMAGE_NAME}:sha-${GITHUB_SHA}" \
            -t "${IMAGE_NAME}:main" .
```

`run: |` giữ các dòng của shell script; dấu `\` cuối dòng nối các phần thành một lệnh Docker build. Không thêm khoảng trắng sau dấu `\`.

Các biến dùng trong shell:

- `IMAGE_NAME`: biến cấp workflow đã đặt là `ghcr.io/${{ github.repository }}`.
- `GITHUB_SHA`: biến GitHub cấp cho commit được workflow build.
- `GITHUB_REPOSITORY`: biến GitHub cấp có dạng `owner/repository`.

Image được build một lần với hai tag:

```text
ghcr.io/todicode/multi-cloud-failover:sha-<full-commit-sha>
ghcr.io/todicode/multi-cloud-failover:main
```

Tag `sha-...` giúp tra cứu image theo commit. Tag `main` là tên tiện dụng và có thể trỏ tới image mới sau lần publish khác; nó không cố định nội dung. Phần tiếp theo sẽ lưu digest để chọn đúng nội dung image khi triển khai.

Hai OCI labels ghi source repository và revision vào metadata của image. Label source hỗ trợ liên kết package với repository khi publish GHCR. Labels này là metadata image, không tự đặt biến môi trường `COMMIT_SHA` cho FastAPI.

### 12.2. Thêm bước push

Đặt sau bước build, cùng mức thụt lề với các dòng `- name` khác:

```yaml
      - name: Push application image
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          docker push "${IMAGE_NAME}:sha-${GITHUB_SHA}"
          docker push "${IMAGE_NAME}:main"
```

Chỉ push sau khi build thành công và khi sự kiện là push vào `main`. Pull request vẫn build image trên runner nhưng bỏ qua cả login và push. Các lệnh push dùng thông tin xác thực do bước `docker/login-action` chuẩn bị.

Hai lệnh publish hai tag của cùng image, không build thêm một bản ứng dụng khác. Khi layer đã có trên registry, log có thể hiện `Layer already exists`.

### 12.3. Đối chiếu job container

```yaml
  container:
    needs: test
    runs-on: ubuntu-latest

    permissions:
      contents: read
      packages: write

    steps:
      - name: Check out source
        uses: actions/checkout@v7

      - name: Log in to GHCR
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build application image
        run: |
          docker build --platform linux/amd64 \
            --label "org.opencontainers.image.source=https://github.com/${GITHUB_REPOSITORY}" \
            --label "org.opencontainers.image.revision=${GITHUB_SHA}" \
            -t "${IMAGE_NAME}:sha-${GITHUB_SHA}" \
            -t "${IMAGE_NAME}:main" .

      - name: Push application image
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          docker push "${IMAGE_NAME}:sha-${GITHUB_SHA}"
          docker push "${IMAGE_NAME}:main"
```

Giữ job `test` và khối `env.IMAGE_NAME` cấp workflow đã viết trước đó. Kiểm tra file:

```bash
cat .github/workflows/container.yml
```

Tới đây đã mô tả đường publish, chưa xác nhận image tồn tại trên GHCR. Bước tiếp theo kiểm tra file rồi commit/push để chạy lần phát hành đầu tiên, sau đó lưu digest và kiểm tra image kéo lại từ registry.

## 13. Chạy lần phát hành GHCR đầu tiên

Trước khi push workflow, kiểm tra:

- Biến `IMAGE_NAME` ở cấp workflow và đúng namespace của repository.
- Job `container` có quyền `contents: read`, `packages: write` và phụ thuộc `test`.
- Login và push cùng điều kiện chỉ chạy từ push vào `main`.
- Build tạo hai tag GHCR, có source/revision labels.
- Các dòng trống không còn khoảng trắng thừa, đặc biệt giữa bước build và bước push.

Thêm rõ các file workflow/tài liệu đang thay đổi vào commit:

```bash
git add -- .github/workflows/container.yml README.md docs/ROADMAP.md docs/instruction/giaidoan3_ci_va_container_registry.md
git diff --cached --check
```

Nếu kiểm tra báo whitespace, sửa file tương ứng rồi chạy lại `git add` và kiểm tra. Khi không báo lỗi:

```bash
git commit -m "ci: publish application image to GHCR"
git push origin main
```

Mở Actions → workflow `Test and publish container` → lượt chạy của commit mới. Job `test` cần đạt trước. Trong job `container`, kiểm tra lần lượt:

1. Checkout source.
2. `Log in to GHCR` thành công.
3. `Build application image` thành công.
4. `Push application image` thành công cho cả hai tag.

Log push cần thể hiện image repository `ghcr.io/todicode/multi-cloud-failover` và digest dạng `sha256:...` cho các tag. `Layer already exists` là kết quả bình thường khi layer đã có. Job xanh do push bị skip trên pull request không chứng minh image đã phát hành; dùng lượt chạy từ push vào `main` để nghiệm thu bước này.

Mở repository trên GitHub và tìm mục Packages. Package `multi-cloud-failover` cần có hai tag:

```text
main
sha-<full-commit-sha>
```

Ghi lại link workflow run, commit SHA và digest từ log push. Lần publish đầu tiên thường tạo package với quyền truy cập private; trạng thái repository public không tự chứng minh image có thể pull ẩn danh. Bước sau sẽ lưu định danh image và kiểm tra pull/runtime với quyền truy cập phù hợp.

Image mới nằm trên GHCR, không tự chạy trên Windows hoặc trên cloud. Hai container lab hiện tại vẫn dùng image local đã tạo ở giai đoạn 2.

## 14. Kéo image đã phát hành bằng digest

### 14.1. Định danh của lần phát hành đã kiểm chứng

Lượt chạy đầu tiên đã xác nhận test, login, build và push đều thành công:

| Trường | Giá trị |
|---|---|
| Workflow run | [42070998760](https://github.com/todicode/multi-cloud-failover/actions/runs/42070998760) |
| Commit | `04596e5e7d5194d9e950b1859545be537893bb8e` |
| Image | `ghcr.io/todicode/multi-cloud-failover` |
| Digest | `sha256:726894c0cb50d04a87b52e64e0025e6c1daebe784fc1089b1c89f6a3d7aa0afd` |

Registry đã trả về manifest theo tag commit cho truy cập ẩn danh, với digest nêu trên. Với lần phát hành mới, ghi nhận digest từ chính lượt chạy hoặc registry của bản đó, không suy ra từ tag `main` sau khi tag đã được cập nhật.

Tag `main` và tag `sha-<commit>` là tên tham chiếu. Digest xác định nội dung manifest cụ thể. Dùng cú pháp `image@sha256:...` để chọn đúng bản đã ghi nhận cho việc kiểm thử và triển khai.

### 14.2. Pull trên máy cá nhân

Docker Desktop cần đang chạy Linux containers. Trong Git Bash:

```bash
docker pull --platform linux/amd64 ghcr.io/todicode/multi-cloud-failover@sha256:726894c0cb50d04a87b52e64e0025e6c1daebe784fc1089b1c89f6a3d7aa0afd
```

Lệnh tải image đã build trên GitHub về Docker image store của máy, không build lại source và không thay đổi container lab đang chạy. Docker có thể dùng lại layer đã có; không cần xóa image local để thực hiện bài này.

Kết quả cần thể hiện đúng digest và pull kết thúc thành công. Nếu nội dung đã có, thông báo image up to date là hợp lệ. Kết quả pull chưa chứng minh ứng dụng đã khởi động được.

Kiểm tra thông tin nền tảng/user và revision label sau khi pull thành công:

```bash
docker image inspect ghcr.io/todicode/multi-cloud-failover@sha256:726894c0cb50d04a87b52e64e0025e6c1daebe784fc1089b1c89f6a3d7aa0afd --format '{{.Os}}/{{.Architecture}} user={{.Config.User}}'
docker image inspect ghcr.io/todicode/multi-cloud-failover@sha256:726894c0cb50d04a87b52e64e0025e6c1daebe784fc1089b1c89f6a3d7aa0afd --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'
```

Giá trị cần có là `linux/amd64 user=appuser` và revision `04596e5e7d5194d9e950b1859545be537893bb8e`.

Nếu tái tạo với package private, cần xác thực có quyền đọc package trước khi pull. Với bản đã kiểm chứng ở trên, registry cho phép truy cập ẩn danh nên không cần tạo token cho bước pull local này.

Bước tiếp theo chạy container từ chính tham chiếu digest để kiểm tra HTTP và database. Sau đó bổ sung phép kiểm tra image đã phát hành trên runner riêng để hoàn thiện pipeline.

## 15. Chạy image đã pull và kiểm tra runtime

### 15.1. Chạy container kiểm tra

Điều kiện: image ở mục 14 đã pull thành công, hai database của lab đang chạy đúng topology AWS primary/Azure standby, network `mcf-todicode_default` tồn tại và `.env.aws.local` đã cấu hình kết nối `database:5432`.

Tạo container tạm từ chính digest đã ghi nhận. Cổng 8380 được chọn riêng với hai container web lab đang dùng 8280/8281:

```bash
docker run -d --name mcf-registry-smoke \
  --network mcf-todicode_default \
  --env-file .env.aws.local \
  -e APP_ENV=registry-smoke \
  -p 127.0.0.1:8380:8080 \
  ghcr.io/todicode/multi-cloud-failover@sha256:726894c0cb50d04a87b52e64e0025e6c1daebe784fc1089b1c89f6a3d7aa0afd
```

`--env-file` dùng lại kết nối primary của lab. `-e APP_ENV=registry-smoke` ghi đè nhãn môi trường trong file cho container kiểm tra này. Container chạy image đã phát hành, kết nối database có sẵn và không yêu cầu build lại source.

Nếu tên container đã tồn tại, kiểm tra trạng thái/log của container đó trước khi tạo lại. Cổng 8380 cần chưa bị tiến trình khác sử dụng.

### 15.2. Kiểm tra ứng dụng

Sau khi ứng dụng khởi động:

```bash
curl -fsS http://127.0.0.1:8380/health/live
curl -fsS http://127.0.0.1:8380/version
curl -fsS http://127.0.0.1:8380/api/database/status
```

Kết quả cần có:

| Kiểm tra | Giá trị cần xác nhận |
|---|---|
| Liveness | HTTP 200, `status=alive` |
| Version | HTTP 200, `environment=registry-smoke` |
| Database status | HTTP 200, `connected=true`, `role=primary`, `writable=true` |

`commit_sha` trong `/version` vẫn có thể là `not-built`, vì Dockerfile hiện chưa đưa commit vào biến runtime. Việc đối chiếu commit của image ở bước này dùng OCI revision label đã kiểm tra tại mục 14.2; label và biến ứng dụng là hai cơ chế riêng.

Mở [http://127.0.0.1:8380/issues.html](http://127.0.0.1:8380/issues.html) để xác nhận static UI và danh sách dữ liệu lab được phục vụ. Nếu cần kiểm tra API đọc trực tiếp:

```bash
curl -fsS http://127.0.0.1:8380/api/issues
```

Có thể kiểm tra UID thực tế của user chạy lệnh trong container:

```bash
docker exec mcf-registry-smoke id -u
```

Giá trị cần có là `10001`, tương ứng với `appuser` trong Dockerfile.

Nếu HTTP hoặc database status lỗi, xem log:

```bash
docker logs --tail 50 mcf-registry-smoke
```

### 15.3. Kết thúc bài kiểm tra local

Chỉ ghi nhận runtime đạt sau khi các kết quả HTTP/database đúng. Khi đã kiểm tra xong, dừng và xóa container tạm nếu không còn cần:

```bash
docker stop mcf-registry-smoke
docker rm mcf-registry-smoke
```

Hai web lab, PostgreSQL và application image vẫn được giữ lại. Bước sau bổ sung xác nhận image đã phát hành trên runner mới để pipeline tự kiểm tra đường phân phối, thay vì chỉ dựa vào phép thử local.

## 16. Xuất tham chiếu image cho job kiểm tra độc lập

Để job mới kiểm tra đúng image vừa publish, job `container` cần xuất giá trị có dạng `ghcr.io/...@sha256:...`. Không ghi cố định digest của lần publish đầu vào workflow vì mỗi lần build có thể tạo nội dung image mới.

### 16.1. Lấy RepoDigest sau bước push

Trong `steps` của job `container`, thêm sau `Push application image`:

```yaml
      - name: Record published image
        id: image
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          image_ref=$(docker image inspect "${IMAGE_NAME}:sha-${GITHUB_SHA}" --format '{{index .RepoDigests 0}}')
          echo "image_ref=${image_ref}" >> "$GITHUB_OUTPUT"
          echo "Published image: ${image_ref}"
```

`docker image inspect` đọc metadata của image trên runner sau khi push. `.RepoDigests` chứa các tham chiếu repository kèm digest; `index ... 0` lấy tham chiếu đầu tiên. Trong job này image chỉ được publish vào cùng một GHCR repository với hai tag.

`image_ref=$(...)` lấy output lệnh vào biến shell. Dòng ghi vào `$GITHUB_OUTPUT` tạo step output tên `image_ref`. `id: image` là ID để các biểu thức workflow tham chiếu step; khác với `name`, là nhãn hiển thị trong log. Dòng echo cuối in tham chiếu đã chọn để tra cứu.

Điều kiện `if` giống step push, nên chỉ ghi nhận định danh sau lần phát hành từ push vào `main`. Pull request không publish và step này cũng bị skip.

### 16.2. Đưa step output ra job output

Trong job `container`, thêm khối sau dưới `runs-on`, cùng mức với `permissions` và `steps`:

```yaml
    outputs:
      image_ref: ${{ steps.image.outputs.image_ref }}
```

`steps.image.outputs.image_ref` đọc output của step có `id: image`. Khối `outputs` công bố giá trị đó ra ngoài job `container`. Job phụ thuộc sau này sẽ đọc bằng `needs.container.outputs.image_ref`.

Luồng dữ liệu:

```text
Push GHCR → inspect RepoDigest → step image output
                                      ↓
                         container job output image_ref
                                      ↓
                         job mới pull đúng image@digest
```

Output truyền chuỗi định danh, không truyền image hoặc file từ runner này sang runner khác. Job kiểm tra phải thực sự pull image từ registry. Job đó cũng cần điều kiện chỉ chạy khi có publish để không đọc output rỗng ở pull request.

Kiểm tra file đã lưu:

```bash
cat .github/workflows/container.yml
```

Tới đây mới xuất định danh; phần tiếp theo thêm job kiểm tra độc lập và các lệnh HTTP. Hoàn thiện job đó trước khi commit/push kiểm chứng toàn bộ đường phân phối.

## 17. Tạo job pull image trên runner riêng

Sau khi job `container` đã khai báo output `image_ref` và step `Record published image`, thêm job sau vào cuối workflow, bên dưới job `container`:

```yaml
  verify-image:
    needs: container
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest

    env:
      IMAGE_REF: ${{ needs.container.outputs.image_ref }}

    steps:
      - name: Pull published image
        run: docker pull --platform linux/amd64 "$IMAGE_REF"
```

`verify-image:` cùng mức thụt lề với `test:` và `container:`, đều nằm trong một khối `jobs` duy nhất.

| Thành phần | Vai trò |
|---|---|
| `needs: container` | Chờ job publish hoàn thành thành công và cho phép đọc outputs của job đó |
| `if` | Chỉ chạy khi có publish từ push vào `main`; tránh đọc output rỗng ở pull request |
| `runs-on: ubuntu-latest` | Dùng runner khác với job build/publish |
| `IMAGE_REF` | Biến môi trường của job, nhận chuỗi `image@digest` từ job trước |
| `docker pull` | Tải đúng image đã phát hành từ GHCR về runner kiểm tra |

Biểu thức `${{ needs.container.outputs.image_ref }}` được GitHub giải quyết để đặt biến môi trường. Trong lệnh Bash, `$IMAGE_REF` đọc giá trị biến đó.

Job này không checkout source và không build image. Runner mới pull từ registry thay vì dùng image còn trong Docker image store của runner build. Package đã kiểm chứng ở mục 14 cho phép đọc ẩn danh, nên job pull này không cần đăng nhập GHCR.

Luồng workflow sau khi thêm job:

```text
test → container: build/push và xuất image_ref → verify-image: pull image_ref
```

Tới đây `verify-image` mới kiểm tra được đường tải image, chưa xác nhận khởi động ứng dụng. Phần tiếp theo bổ sung chạy container và kiểm tra HTTP trước khi commit/push nghiệm thu cả pipeline.

Kiểm tra nội dung đã lưu:

```bash
cat .github/workflows/container.yml
```

## 18. Chạy container và kiểm tra HTTP trên runner mới

Trong `steps` của job `verify-image`, thêm hai bước sau dưới `Pull published image`:

```yaml
      - name: Start published application
        run: |
          docker run -d --name mcf-ci-verify \
            -p 127.0.0.1:18080:8080 \
            -e APP_ENV=ci-clean-pull \
            -e APP_REGION=github-actions \
            "$IMAGE_REF"

      - name: Check published application HTTP
        run: |
          curl -fsS --retry 10 --retry-all-errors --retry-delay 2 --max-time 5 \
            http://127.0.0.1:18080/health/live
          curl -fsS --max-time 5 http://127.0.0.1:18080/version
          curl -fsS --max-time 5 http://127.0.0.1:18080/issues.html -o /dev/null
```

### 18.1. Khởi động image đã phát hành

`docker run` sử dụng đúng `IMAGE_REF` nhận từ job publish, không dùng tag có thể thay đổi như `main`. Container tạm tên `mcf-ci-verify` publish cổng 18080 trên loopback của runner tới cổng 8080 của ứng dụng.

`APP_ENV=ci-clean-pull` và `APP_REGION=github-actions` là identity của phép kiểm tra này. Lệnh run dùng `CMD` đã có trong image để khởi động Uvicorn. Không cần checkout source, setup Python trên runner hoặc cài dependency lại.

### 18.2. Chờ khởi động và kiểm tra HTTP

| Tùy chọn curl | Ý nghĩa |
|---|---|
| `-f` | Trả mã lỗi khi HTTP response báo lỗi từ 400 trở lên |
| `-sS` | Bỏ progress meter nhưng vẫn hiển thị thông báo lỗi |
| `--retry 10` | Cho phép retry tối đa 10 lần với các lỗi đủ điều kiện retry |
| `--retry-all-errors` | Cho phép retry mọi lỗi curl trong phép GET liveness, gồm connection refused và connection reset |
| `--retry-delay 2` | Chờ 2 giây giữa các lần retry |
| `--max-time 5` | Giới hạn thời gian mỗi lần truyền request ở mức 5 giây |
| `-o /dev/null` | Không in HTML ra log, vẫn kiểm tra kết quả HTTP |

Liveness có retry để chờ ứng dụng sẵn sàng sau `docker run`. Docker có thể đã publish cổng trước khi Uvicorn bắt đầu nhận request; request quá sớm có thể bị từ chối hoặc bị reset. `docker run -d` trả thành công không chứng minh HTTP đã sẵn sàng. Khi liveness đã đạt, hai request tiếp theo kiểm tra version và static UI. Lệnh curl vẫn lỗi sau số lần thử cho phép làm step thất bại theo cách runner thực thi shell script hiện tại.

`--retry-all-errors` được dùng cho GET liveness không thay đổi dữ liệu này. Không áp dụng tự động cùng cấu hình retry cho request ghi dữ liệu. Lỗi tạm thời vẫn có thể xuất hiện trong log trước lần thử thành công; tiêu chí là exit code cuối cùng của step.

Kết quả cần quan sát trong log:

- Liveness trả `{"status":"alive"}`.
- Version có `environment=ci-clean-pull` và `region=github-actions`.
- Trang `/issues.html` trả thành công; HTML được bỏ khỏi log.

Các lệnh curl hiện kiểm tra HTTP thành công và in JSON để đối chiếu; chưa tự assert tất cả trường JSON hoặc nội dung HTML. Các kiểm tra API chi tiết đã nằm trong job `test`.

Job này không có PostgreSQL service hoặc network của lab local. Smoke check tập trung vào khả năng phân phối và khởi động web; kết nối database của image đã được kiểm tra local ở mục 15, còn integration test API/PostgreSQL chạy ở job `test`. Không dùng `/health/database` làm tiêu chí của job smoke khi chưa cấu hình database cho nó.

Luồng kiểm tra:

```text
Runner mới → pull image@digest → chạy container → health/version/static UI
```

Kiểm tra nội dung file sau khi thêm:

```bash
cat .github/workflows/container.yml
```

Bước tiếp theo hoàn thiện đối chiếu identity của image và xử lý log/cleanup, rồi mới commit/push để nghiệm thu cả pipeline.

## 19. Đối chiếu image và dọn container kiểm tra

### 19.1. Kiểm tra metadata sau khi pull

Trong job `verify-image`, thêm step sau **giữa** `Pull published image` và `Start published application`:

```yaml
      - name: Check image identity
        run: |
          revision=$(docker image inspect "$IMAGE_REF" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')
          echo "Image revision: $revision"
          test "$revision" = "$GITHUB_SHA"
          test "$(docker image inspect "$IMAGE_REF" --format '{{.Config.User}}')" = "appuser"
```

`revision` đọc OCI label đã được gắn khi build. `GITHUB_SHA` là commit của workflow đang chạy. Lệnh `test` trả mã 0 nếu hai giá trị bằng nhau; nếu khác, step thất bại. Phép kiểm tra thứ hai xác nhận user mặc định trong cấu hình image là `appuser`, đúng với Dockerfile.

Job pull theo digest để xác định nội dung image; kiểm tra label bổ sung đối chiếu commit mà image khai báo. Label là metadata do bước build cung cấp, không phải chữ ký chứng thực độc lập. Phép kiểm tra user đọc cấu hình mặc định của image, không kiểm tra mọi hành vi phân quyền của ứng dụng.

OCI label này khác biến môi trường `COMMIT_SHA` mà API `/version` đọc. Dockerfile hiện chưa gán biến đó, nên API vẫn có thể trả `commit_sha=not-built` trong khi OCI label chứa đúng commit.

### 19.2. Xem log và dọn container dù kiểm tra thất bại

Thêm step sau **cuối** danh sách `steps` của `verify-image`, sau `Check published application HTTP`:

```yaml
      - name: Show logs and clean up
        if: always()
        run: |
          docker logs mcf-ci-verify || true
          docker rm -f mcf-ci-verify || true
```

`if: always()` cho phép step này chạy cả khi step trước thất bại. Log giúp xác định lỗi khởi động hoặc HTTP. `docker rm -f` dừng và xóa container tạm có tên cụ thể.

`|| true` cho phép tiếp tục nếu container chưa được tạo, chẳng hạn do pull image lỗi. Chỉ hai lệnh log/cleanup được bỏ qua lỗi; một step kiểm tra đã thất bại trước đó vẫn làm job thất bại.

Thứ tự các step sau khi hoàn thiện:

```text
Pull published image
→ Check image identity
→ Start published application
→ Check published application HTTP
→ Show logs and clean up
```

Kiểm tra thay đổi trước khi commit:

```bash
git diff --check
git diff -- .github/workflows/container.yml
```

Chỉ đánh dấu hoàn thành giai đoạn khi workflow đã được push và cả ba job `test`, `container`, `verify-image` thành công trên GitHub Actions.

### 19.3. Xử lý lỗi curl 56 trong lúc chờ ứng dụng khởi động

Nếu `Check published application HTTP` dừng ngay với `curl: (56) Recv failure: Connection reset by peer`, kiểm tra cấu hình retry và log ứng dụng. `--retry-connrefused` chỉ mở rộng retry cho connection refused, không bao gồm mọi lỗi nhận dữ liệu như connection reset.

Trong step HTTP, dùng dòng liveness ở mục 18 với `--retry 10 --retry-all-errors`. Hai request version và static UI giữ nguyên. Đây là cơ chế chờ có giới hạn; nếu ứng dụng crash hoặc không phục vụ HTTP, step vẫn thất bại sau các lần thử.

Mở `Show logs and clean up` của lần chạy lỗi để xem log Uvicorn. Traceback hoặc lỗi import cần được xử lý theo log, không kết luận mọi connection reset đều do khởi động chậm. Sau khi sửa cấu hình chờ, commit lại và push để GitHub chạy phiên bản workflow mới:

```bash
git add -- .github/workflows/container.yml docs/instruction/giaidoan3_ci_va_container_registry.md
git diff --cached --check
git commit -m "fix(ci): retry connection resets during startup checks"
git push origin main
```

Re-run một workflow cũ vẫn dùng cấu hình của commit cũ. Dùng lần chạy của commit sửa lỗi để nghiệm thu.

## 20. Commit, push và nghiệm thu pipeline

Sau khi đã thêm đủ các step của job `verify-image`, đưa workflow và tài liệu vào cùng commit. Chạy trong Git Bash từ thư mục gốc repository:

```bash
git add -- .github/workflows/container.yml README.md docs/ROADMAP.md docs/instruction/giaidoan3_ci_va_container_registry.md
git diff --cached --check
```

Nếu lệnh kiểm tra không báo lỗi whitespace, tiếp tục:

```bash
git commit -m "ci: verify published image on a separate runner"
git push origin main
```

Tiền tố `ci:` thể hiện thay đổi chính thuộc pipeline tích hợp và kiểm tra tự động. Cảnh báo LF/CRLF của Git trên Windows không đồng nghĩa với lỗi trailing whitespace; nếu có lỗi `trailing whitespace`, sửa dòng được báo rồi stage và kiểm tra lại trước khi commit.

Mở [GitHub Actions của repository](https://github.com/todicode/multi-cloud-failover/actions), chọn lần chạy ứng với commit vừa push. Luồng cần thành công:

```text
test → container → verify-image
```

| Job | Tiêu chí nghiệm thu |
|---|---|
| `test` | Chạy bộ test API và integration test với PostgreSQL service thành công |
| `container` | Build/push GHCR thành công; `Record published image` in tham chiếu `ghcr.io/...@sha256:...` |
| `verify-image` | Pull đúng tham chiếu từ job trước, đối chiếu revision/user, khởi động container và kiểm tra HTTP thành công |

Trong `verify-image`, xem log `Check published application HTTP`: liveness trả `alive`, version có environment `ci-clean-pull` và region `github-actions`. Step kiểm tra static UI thành công khi request `/issues.html` không lỗi. `Show logs and clean up` phải chạy sau phần kiểm tra; riêng step cleanup xanh không chứng minh các step trước thành công.

Lưu liên kết workflow run, commit SHA và image digest trong ghi chép nghiệm thu. Image ở lần build này có thể mang digest khác lần publish đầu; lấy giá trị của đúng run đã kiểm chứng để triển khai sau này.

Nếu một job đỏ, mở step lỗi đầu tiên và đọc log trước khi chạy lại. Không đánh dấu hoàn thành bằng kết quả kiểm tra cú pháp local: giai đoạn này cần bằng chứng cả ba job thành công trên GitHub. Workflow hiện kiểm tra/phát hành image; chưa triển khai tài nguyên AWS hoặc Azure.

## 21. Theo dõi tiến độ

- [x] Tạo file và hiểu tên workflow, sự kiện kích hoạt, quyền đọc source.
- [x] Bổ sung job Linux và checkout source.
- [x] Chuẩn bị Python runtime và dependency.
- [x] Cấu hình PostgreSQL service và chạy test trên GitHub.
- [x] Build image trên GitHub sau khi test đạt.
- [x] Phát hành GHCR và lưu digest/commit.
- [x] Pull image bằng digest và xác nhận runtime/database local.
- [ ] Xác nhận pipeline đầy đủ test/build/publish/kiểm tra runtime thành công.

Hướng dẫn cho các phần chưa thực hành sẽ được bổ sung theo tiến độ. Checklist không thay thế kết quả chạy workflow.
