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
