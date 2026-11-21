# Giai đoạn 8 — Giám sát độc lập

## Bước 1 — Kiểm tra HTTPS với Blackbox Exporter

Blackbox Exporter chạy trên laptop để kiểm tra ba địa chỉ công khai từ bên ngoài hai cloud. Endpoint `/health/live` cho biết ứng dụng có trả lời hay không. Endpoint `/health/database` cho biết origin đó có đang nhận ghi hay không.

### Cấu hình probe

File `observability/blackbox.yml`:

```yaml
modules:
  https_200:
    prober: http
    timeout: 5s
    http:
      method: GET
      valid_status_codes: [200]
      follow_redirects: false
      fail_if_not_ssl: true
      preferred_ip_protocol: ip4
      ip_protocol_fallback: false
```

Module `https_200` gửi một request GET qua IPv4 cho mỗi lượt probe. Kết quả đạt khi đích trả HTTP 200 qua TLS trong vòng 5 giây. Giá trị `follow_redirects: false` giữ mã phản hồi của URL ban đầu.

### Chạy container trên laptop

Cấu hình `observability/compose.yaml` đã kiểm tra ở bước này:

```yaml
name: mcf-observability

services:
  blackbox:
    image: prom/blackbox-exporter:v0.28.0
    command:
      - --config.file=/etc/blackbox_exporter/config.yml
    ports:
      - "127.0.0.1:19115:9115"
    volumes:
      - ./blackbox.yml:/etc/blackbox_exporter/config.yml:ro
```

Cổng `19115` trên loopback của laptop chuyển request vào cổng `9115` của container. Exporter đọc file cấu hình được gắn vào container dưới dạng chỉ đọc.

Từ Git Bash tại thư mục gốc của repo, chạy:

```bash
docker compose -f observability/compose.yaml config --quiet \
  && docker compose -f observability/compose.yaml up -d

docker compose -f observability/compose.yaml ps
```

### Kiểm tra từng đích

```bash
probe() {
  printf '\n%s\n' "$1"
  /c/Windows/System32/curl.exe -fsS -G \
    'http://127.0.0.1:19115/probe' \
    --data-urlencode 'module=https_200' \
    --data-urlencode "target=$1" |
    grep -E '^probe_(http_status_code|success) '
}

probe https://app.mcf.todicode.tech/health/live
probe https://aws.mcf.todicode.tech/health/live
probe https://azure.mcf.todicode.tech/health/live
probe https://aws.mcf.todicode.tech/health/database
probe https://azure.mcf.todicode.tech/health/database
```

`curl` gọi endpoint `/probe` của exporter trên laptop và truyền đích qua tham số `target`. Exporter gọi URL đích và trả mã HTTP qua metric `probe_http_status_code`, cùng kết luận của module qua `probe_success`.

### Kết quả thực tế

| Đích | `probe_http_status_code` | `probe_success` |
|---|---:|---:|
| Tên miền chung `/health/live` | 200 | 1 |
| AWS `/health/live` | 200 | 1 |
| Azure `/health/live` | 200 | 1 |
| AWS `/health/database` | 200 | 1 |
| Azure `/health/database` | 503 | 0 |

Cả ba đích trả HTTP 200 cho liveness. Trong trạng thái đã nghiệm thu, AWS nhận ghi và Azure đang là standby. Cặp tín hiệu liveness 1 và writer 0 trên Azure thể hiện app truy cập được trong khi database ở chế độ chỉ đọc.

## Bước 2 — Thu thập và lưu kết quả bằng Prometheus

Prometheus chạy trên laptop cùng Blackbox Exporter. Mỗi 10 giây, Prometheus yêu cầu exporter kiểm tra từng URL và lưu các mẫu đo kèm nhãn `site` và `check`. Hai nhãn này cho phép lọc theo cloud và theo loại kiểm tra trong PromQL.

### Thêm Prometheus vào Compose

Thêm service sau bên dưới service `blackbox` trong `observability/compose.yaml` và khai báo volume ở cấp cao nhất.

```yaml
  prometheus:
    image: prom/prometheus:v3.16.0
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
    ports:
      - "127.0.0.1:19090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus

volumes:
  prometheus_data:
```

Cổng `19090` mở giao diện Prometheus trên laptop. Volume `prometheus_data` giữ các mẫu đo khi container được tạo lại.

### Cấu hình thu thập

Thêm nội dung sau vào `observability/prometheus.yml`.

```yaml
global:
  scrape_interval: 10s
  scrape_timeout: 8s

storage:
  tsdb:
    retention:
      time: 7d

scrape_configs:
  - job_name: blackbox_https
    metrics_path: /probe
    params:
      module: [https_200]
    static_configs:
      - targets: ["https://app.mcf.todicode.tech/health/live"]
        labels: {site: shared, check: liveness}
      - targets: ["https://aws.mcf.todicode.tech/health/live"]
        labels: {site: aws, check: liveness}
      - targets: ["https://azure.mcf.todicode.tech/health/live"]
        labels: {site: azure, check: liveness}
      - targets: ["https://aws.mcf.todicode.tech/health/database"]
        labels: {site: aws, check: writer}
      - targets: ["https://azure.mcf.todicode.tech/health/database"]
        labels: {site: azure, check: writer}
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox:9115
```

Ba quy tắc `relabel_configs` lần lượt đưa URL đích vào tham số `target`, giữ URL đó trong nhãn `instance` và gửi request scrape đến `blackbox:9115` qua mạng Compose. Prometheus chờ tối đa 8 giây cho mỗi lượt scrape và giữ dữ liệu trong 7 ngày.

### Chạy và xác nhận kết quả

```bash
docker compose -f observability/compose.yaml up -d
docker compose -f observability/compose.yaml ps
```

Mở giao diện tại `http://127.0.0.1:19090` và chạy riêng từng truy vấn.

```promql
up{job="blackbox_https"}
```

```promql
probe_success{job="blackbox_https"}
```

Kết quả ghi nhận từ giao diện Prometheus có đủ 5 chuỗi cho mỗi truy vấn.

| `site` | `check` | `up` | `probe_success` |
|---|---|---:|---:|
| `aws` | `liveness` | 1 | 1 |
| `azure` | `liveness` | 1 | 1 |
| `shared` | `liveness` | 1 | 1 |
| `aws` | `writer` | 1 | 1 |
| `azure` | `writer` | 1 | 0 |

`up=1` cho biết Prometheus đã thu được các metric từ exporter. `probe_success` là kết luận kiểm tra URL đích. Trong lần quan sát này, ba endpoint liveness đều đạt, AWS nhận ghi và Azure đang là standby.

## Bước 3 — Giám sát kết nối replication

Kiểm tra trạng thái PostgreSQL trên cả AWS và Azure để theo dõi standby ngay cả khi hai cloud đổi vai trò. API `/api/database/status` cho biết vai trò của database và đặt `replication_connected=true` khi WAL receiver đang ở trạng thái `streaming`.

Thêm module sau vào `observability/blackbox.yml` dưới `modules:`, cùng cấp với `https_200`.

```yaml
  https_standby_streaming:
    prober: http
    timeout: 5s
    http:
      method: GET
      valid_status_codes: [200]
      follow_redirects: false
      fail_if_not_ssl: true
      preferred_ip_protocol: ip4
      ip_protocol_fallback: false
      fail_if_body_json_not_matches_cel: >-
        body.connected == true &&
        body.role == "standby" &&
        body.replication_connected == true
```

Probe yêu cầu HTTP 200 qua TLS và kiểm tra ba trường trong JSON trả về. Hai LSN `receive_lsn` và `replay_lsn` có thể dùng để xem tiến độ xử lý WAL trên standby. Tín hiệu ở đây chỉ đo trạng thái kết nối.

Thêm job sau vào `observability/prometheus.yml` dưới `scrape_configs:`, cùng cấp với `blackbox_https`.

```yaml
  - job_name: blackbox_replication
    metrics_path: /probe
    params:
      module: [https_standby_streaming]
    static_configs:
      - targets: ["https://aws.mcf.todicode.tech/api/database/status"]
        labels: {site: aws, check: replication}
      - targets: ["https://azure.mcf.todicode.tech/api/database/status"]
        labels: {site: azure, check: replication}
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox:9115
```

Tạo lại hai container để nạp cấu hình. Volume Prometheus giữ dữ liệu đã thu thập.

```bash
docker compose -f observability/compose.yaml up -d --force-recreate blackbox prometheus
```

Chờ ít nhất một chu kỳ scrape rồi chạy riêng hai truy vấn trong Prometheus.

```promql
up{job="blackbox_replication"}
```

```promql
probe_success{job="blackbox_replication"}
```

Kết quả quan sát được khi AWS là primary và Azure là standby.

| `site` | `up` | `probe_success` | Ý nghĩa |
|---|---:|---:|---|
| `aws` | 1 | 0 | Prometheus nhận được kết quả và AWS đang là primary |
| `azure` | 1 | 1 | Prometheus nhận được kết quả và Azure đang là standby có WAL receiver streaming |

Đọc kết quả cạnh tín hiệu `writer` để phân biệt primary đang nhận ghi, standby đang nhận WAL và trường hợp mất kết nối replication.

## Bước 4 — Nối Grafana với Prometheus và xem độ trễ HTTPS

Grafana truy vấn các mẫu Prometheus đã lưu và hiển thị chúng theo thời gian. Tạo file `observability/grafana/datasources/prometheus.yml` để Grafana nạp nguồn dữ liệu khi khởi động.

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    uid: mcf-prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

`access: proxy` cho Grafana gửi truy vấn từ container. Địa chỉ `prometheus:9090` dùng tên service và cổng nội bộ trên mạng Compose.

Trong `observability/compose.yaml`, thêm `grafana` vào `services` và khai báo `grafana_data` trong khối `volumes` cuối file.

```yaml
  grafana:
    image: grafana/grafana:13.3.1
    ports:
      - "127.0.0.1:13000:3000"
    volumes:
      - ./grafana/datasources:/etc/grafana/provisioning/datasources:ro
      - grafana_data:/var/lib/grafana

volumes:
  prometheus_data:
  grafana_data:
```

Cổng `13000` mở giao diện Grafana trên laptop. Volume `grafana_data` lưu tài khoản và dashboard qua các lần tạo lại container.

```bash
docker compose -f observability/compose.yaml up -d
docker compose -f observability/compose.yaml ps
```

Mở `http://127.0.0.1:13000`, dùng `admin` cho tên và mật khẩu lần đầu, rồi đổi mật khẩu. Vào **Explore**, chọn **Prometheus** và chế độ **Code**, chọn khoảng thời gian **Last 15 minutes**, sau đó chạy truy vấn sau.

```promql
1000 * probe_duration_seconds{job="blackbox_https", check="liveness"}
```

Phép nhân đổi thời gian thực hiện toàn bộ lượt probe từ giây sang mili giây. Khi **Type** là **Both**, phần **Graph** hiển thị lịch sử theo thời gian và phần **Raw** hiển thị giá trị Instant tại cuối khoảng thời gian đã chọn.

Kết quả ghi nhận trong Grafana Explore có ba chuỗi. Đây là các giá trị Instant tại thời điểm chụp.

| `site` | Thời gian probe |
|---|---:|
| `aws` | 80,62 ms |
| `azure` | 92,70 ms |
| `shared` | 136,81 ms |

Khi thấy độ trễ tăng, đối chiếu với `probe_success` của cùng `site` và `check` tại thời điểm đó để biết probe có đạt hay không.

## Bước 5 — Tạo dashboard giám sát failover

Trong Grafana, tạo dashboard `Multi-Cloud Failover` và thêm ba panel dùng nguồn Prometheus. Mỗi truy vấn chạy ở chế độ **Code** và **Type → Range** để hiển thị các mẫu theo thời gian.

### Liveness

Chọn **State timeline**, đặt tên `Liveness` và dùng `{{site}}` làm chú giải tùy chỉnh.

```promql
probe_success{job="blackbox_https", check="liveness"}
```

Panel có ba hàng `shared`, `aws` và `azure`. Khi test failover, hàng `shared` cho biết probe qua tên miền chung đạt hay thất bại.

### Writer và WAL streaming

Chọn **State timeline**, đặt tên `Database — Writer and WAL Streaming` và dùng `{{site}} · {{check}}` làm chú giải tùy chỉnh.

```promql
probe_success{job="blackbox_https", check="writer"}
or
probe_success{job="blackbox_replication", check="replication"}
```

Truy vấn hợp hai nhóm probe để hiển thị khả năng ghi và kết nối WAL của từng bên. Trong **Standard options**, chọn **Color scheme → From thresholds**. Đặt **Thresholds** ở chế độ **Absolute**, màu xám cho **Base** và màu xanh lá từ mốc `1`. Màu xám thể hiện điều kiện của hàng hiện chưa thỏa. Ví dụ, standby có giá trị `writer=0` trong lúc hoạt động đúng.

### Độ trễ HTTPS

Chọn **Time series**, đặt tên `HTTPS Probe Duration`, dùng chú giải `{{site}}` và chọn đơn vị **milliseconds (ms)**.

```promql
1000 * probe_duration_seconds{job="blackbox_https", check="liveness"}
```

Chọn **Last 15 minutes** rồi lưu dashboard. Trong ảnh nghiệm thu, cả ba hàng liveness đều giữ `1` trong khoảng hiển thị và biểu đồ độ trễ có đủ ba đường. Panel database hiển thị các giá trị sau.

| Cloud | `writer` | `replication` |
|---|---:|---:|
| AWS | 1 | 0 |
| Azure | 0 | 1 |

## Bước 6 — Tự nạp dashboard từ repo

Trong dashboard `Multi-Cloud Failover`, lưu các thay đổi rồi chọn **Export → Export as code**. Chọn **V2 Resource** và định dạng **JSON**. Giữ công tắc **Share dashboard with another instance** ở trạng thái tắt để giữ tham chiếu tới nguồn `mcf-prometheus`. Lưu file tại `observability/grafana/dashboards/multi-cloud-failover.json`.

File `observability/grafana/providers/dashboards.yml` chỉ định đường dẫn Grafana đọc trong container.

```yaml
apiVersion: 1

providers:
  - name: multi-cloud-failover
    type: file
    updateIntervalSeconds: 30
    allowUiUpdates: false
    options:
      path: /opt/mcf/dashboards
```

Trong `observability/compose.yaml`, cấu hình `volumes` của service `grafana` như sau.

```yaml
    volumes:
      - ./grafana/datasources:/etc/grafana/provisioning/datasources:ro
      - ./grafana/providers:/etc/grafana/provisioning/dashboards:ro
      - ./grafana/dashboards:/opt/mcf/dashboards:ro
      - grafana_data:/var/lib/grafana
```

Grafana nạp provider khi khởi động và đọc JSON từ thư mục được mount. JSON là nơi lưu cấu hình dashboard và Grafana kiểm tra thay đổi trên đĩa mỗi 30 giây.

```bash
docker compose -f observability/compose.yaml config --quiet \
  && docker compose -f observability/compose.yaml up -d
docker compose -f observability/compose.yaml ps
docker compose -f observability/compose.yaml logs --tail 80 grafana
```

Lần kiểm tra ghi nhận cả ba container đang chạy, file provider và dashboard có mặt trong container Grafana, API health báo database `ok` và log startup báo hoàn tất provisioning. File dashboard chứa ba panel `Liveness`, `Database — Writer and WAL Streaming` và `HTTPS Probe Duration`.

Để kiểm tra riêng dashboard từ trình duyệt đã đăng nhập Grafana, lấy UID từ URL sau `/d/`, mở `/api/dashboards/uid/<UID>` trên Grafana và kiểm tra `meta.provisioned` là `true`.
