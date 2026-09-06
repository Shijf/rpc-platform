# RPC 系统开发与部署规范

本文档是当前 Ubuntu 服务器上 RPC 系统的长期使用手册。后续创建内部业务服务时，应优先按照本文档的目录结构、命名规则、网络配置和发布流程实现。

当前可运行参考项目：

- [`Shijf/rpc-user-service`](https://github.com/Shijf/rpc-user-service)
- [`Shijf/rpc-order-service`](https://github.com/Shijf/rpc-order-service)
- [`Shijf/rpc-platform`](https://github.com/Shijf/rpc-platform)

---

## 1. 系统目标

这套系统主要解决以下问题：

1. 服务之间不再使用会变化的容器 IP。
2. 每个服务可以独立使用 Git 和 Dokploy 发布。
3. 服务之间使用强类型 RPC 接口，不再随意拼接内部 HTTP 地址和 JSON。
4. 内部 RPC 端口不暴露到宿主机、局域网或公网。
5. 容器重新创建后，服务调用地址保持不变。
6. 接口变更可以进行版本管理和兼容性检查。

推荐调用方式：

```text
user-service:50051
order-service:50051
payment-service:50051
inventory-service:50051
```

禁止在业务代码中保存容器 IP：

```text
10.0.2.12:50051
```

---

## 2. Docker、gRPC 与 Protobuf 的职责

三者不是同一个东西：

| 组件 | 职责 |
|---|---|
| Docker 网络 | 建立容器之间的通信路径 |
| Docker DNS | 把 `user-service` 解析到当前容器地址 |
| gRPC | 远程方法调用、错误码、超时和流式传输 |
| Protobuf | 定义方法、请求和返回值的数据结构 |
| Dokploy | 从 Git 构建、部署、监控和更新服务 |
| Traefik | 处理浏览器或外部客户端进入服务器的 HTTP/HTTPS 请求 |

可以把它理解为：

```text
Docker DNS = 通讯录
Docker 网络 = 道路
gRPC       = 通话协议和调用框架
Protobuf   = 双方共同遵守的话术与数据格式
业务代码   = 真正处理的业务
```

一次 RPC 调用的实际过程：

```text
order-service
    │
    │ 1. 请求连接 user-service:50051
    ▼
Docker 内置 DNS
    │
    │ 2. 解析到 rpc-network 内部地址
    ▼
user-service 容器
    │
    │ 3. gRPC 调用 GetUser()
    ▼
返回 Protobuf User 数据
```

---

## 3. 当前服务器基础设施

### 3.1 RPC 网络

所有内部 RPC 服务使用同一个外部 Docker 网络：

```text
rpc-network
```

该网络目前是：

```text
Driver: overlay
Scope: swarm
Attachable: true
Encrypted: enabled
```

创建命令：

```bash
docker network create \
  --driver overlay \
  --attachable \
  --opt encrypted \
  rpc-network
```

这个命令只需要在服务器初始化时执行一次。各个项目的 `compose.yaml` 使用 `external: true` 加入已有网络，不应该重复创建它。

### 3.2 服务发现

当前没有安装 Nacos 或 Consul。服务发现由 Docker 内置 DNS 完成。

服务必须满足两个条件：

1. 调用方和被调用方都加入 `rpc-network`。
2. 被调用方在该网络上拥有稳定的 DNS 别名。

示例：

```yaml
networks:
  rpc-network:
    aliases:
      - user-service
```

Docker 会自动维护：

```text
user-service → 当前 user-service 容器地址
```

### 3.3 服务中心

服务器浏览器主页：

```text
file:///config/services.html
```

宿主机每 5 分钟读取 Docker 状态并生成页面，浏览器每 2 分钟刷新一次。Dokploy 生成的容器名可能带随机前缀，服务中心通过标准 Compose 标签识别真正的服务名。

---

## 4. 什么场景应该使用 RPC

“内部调用优先 RPC”并不代表所有网络通信都强制改成 gRPC。

### 4.1 推荐使用 RPC

- 用户服务查询用户资料。
- 订单服务创建或查询订单。
- 支付服务发起支付、查询支付状态。
- 商品服务查询库存或商品信息。
- 权限服务判断内部业务权限。
- 多个后端服务之间的同步业务调用。

示例：

```text
order-service → user-service.GetUser()
order-service → inventory-service.ReserveStock()
order-service → payment-service.CreatePayment()
```

### 4.2 不应直接使用内部 gRPC 的场景

| 场景 | 推荐方式 |
|---|---|
| 浏览器访问 | HTTPS + Traefik + HTTP API，或增加 gRPC-Web 网关 |
| MySQL/PostgreSQL | 数据库原生协议，但仅由数据所属服务访问 |
| Redis | Redis 原生协议 |
| 图片和大文件 | MinIO/S3，不要塞进普通 RPC 消息 |
| 长时间异步任务 | 后续引入消息队列，避免长时间阻塞 RPC |
| 对外开放 API | API Gateway/Traefik，内部再转换为 RPC |

外部流量和内部流量应分开：

```text
浏览器
  ↓ HTTPS
Traefik / API Gateway
  ↓ gRPC
内部业务服务
```

---

## 5. 服务与仓库命名规范

### 5.1 Git 仓库

统一使用：

```text
rpc-<领域>-service
```

示例：

```text
rpc-user-service
rpc-order-service
rpc-payment-service
rpc-inventory-service
```

### 5.2 Docker 服务和 DNS 别名

统一使用：

```text
<领域>-service
```

示例：

```text
user-service
order-service
payment-service
inventory-service
```

Dokploy 可能把实际容器命名为：

```text
project-random-user-service-1
```

这没有关系。调用方只使用稳定网络别名：

```text
user-service:50051
```

### 5.3 端口

默认规范：

| 端口 | 用途 | 是否发布到宿主机 |
|---|---|---|
| `50051` | 内部 gRPC | 否 |
| `8080` | `/healthz` 和可选调试页 | 否 |

所有容器都可以使用内部 `50051`，因为每个容器都有独立网络地址。禁止把所有服务映射到宿主机的同一个 `50051`。

推荐：

```yaml
expose:
  - "50051"
  - "8080"
```

禁止：

```yaml
ports:
  - "50051:50051"
```

---

## 6. 新服务标准目录

每个 Python RPC 服务建议使用：

```text
rpc-example-service/
├── .github/
│   └── workflows/
│       └── verify.yml
├── proto/
│   └── example.proto
├── .dockerignore
├── .gitignore
├── app.py
├── compose.yaml
├── Dockerfile
├── README.md
└── requirements.txt
```

当前可以直接参考：

```text
rpc-user-service
rpc-order-service
```

---

## 7. Protobuf 接口规范

### 7.1 基本结构

```protobuf
syntax = "proto3";

package inventory.v1;

service InventoryService {
  rpc GetStock(GetStockRequest) returns (GetStockResponse);
  rpc ReserveStock(ReserveStockRequest) returns (ReserveStockResponse);
}

message GetStockRequest {
  string product_id = 1;
}

message GetStockResponse {
  string product_id = 1;
  int64 available_quantity = 2;
}
```

### 7.2 命名规则

- package 必须带版本，例如 `inventory.v1`。
- Service 使用 PascalCase，并以 `Service` 结尾。
- RPC 方法使用动词开头，例如 `GetUser`、`CreateOrder`。
- 每个 RPC 使用独立的 Request 和 Response。
- 字段使用 `lower_snake_case`。
- 字段编号一旦发布，不得改变含义或重复使用。

### 7.3 兼容性规则

通常安全的变更：

- 增加新的 RPC 方法。
- 给消息增加新的可选字段。
- 增加新的 message。
- 增加新的 enum 值，但客户端必须能处理未知值。

危险或禁止的变更：

- 修改现有字段编号。
- 修改现有字段类型。
- 删除仍被客户端使用的字段。
- 把旧字段编号用于新字段。
- 直接改变 RPC 请求或返回类型。

删除字段时应该保留编号：

```protobuf
message User {
  reserved 3;
  reserved "old_field";
}
```

不兼容升级应该增加包版本：

```text
user.v1
user.v2
```

### 7.4 跨仓库契约

当前系统已经建立独立的 `rpc-contracts` 仓库，两个业务仓库不再各自保存 `.proto`。它的结构如下：

```text
rpc-contracts/
├── proto/                 唯一协议源文件
├── sdk/python/            Python 生成代码和包配置
├── sdk/node/              Node.js/TypeScript 生成代码和包配置
├── sdk/go/                Go 生成代码和 go.mod
├── scripts/generate.sh    lint 并生成三种 SDK
└── scripts/vendor-python.sh
```

`buf lint` 负责风格检查，固定版本的 Buf 远程插件负责生成代码。当前 Python 业务服务使用 vendor 方式携带固定版本 SDK，避免 Dokploy 构建镜像时访问 GitHub 或注入私钥。以后也可以把 SDK 发布到 PyPI、npm、Go module proxy 或 Buf Schema Registry。

原则：提供服务的一方拥有接口定义，调用方消费确定版本的接口，不应该自行修改对方的 Proto。

---

## 8. Python 服务端实现

依赖：

```text
grpcio
grpcio-health-checking
grpcio-reflection
protobuf
```

生成代码不在业务仓库进行，而是在 `rpc-contracts` 一次生成三种语言 SDK：

```bash
cd /home/shijf/rpc-contracts
./scripts/generate.sh
```

服务端示例：

```python
from concurrent import futures

import grpc
from inventory.v1 import inventory_pb2, inventory_pb2_grpc


class InventoryService(inventory_pb2_grpc.InventoryServiceServicer):
    def GetStock(self, request, context):
        return inventory_pb2.GetStockResponse(
            product_id=request.product_id,
            available_quantity=100,
        )


server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
inventory_pb2_grpc.add_InventoryServiceServicer_to_server(
    InventoryService(), server
)
server.add_insecure_port("[::]:50051")
server.start()
server.wait_for_termination()
```

服务必须监听：

```text
0.0.0.0:50051 或 [::]:50051
```

不要只监听：

```text
127.0.0.1:50051
```

否则其他容器无法访问。

---

## 9. Python 客户端调用

调用地址通过环境变量配置，并提供稳定默认值：

```python
import os
import grpc

import user_pb2
import user_pb2_grpc


target = os.environ.get("USER_SERVICE_ADDR", "user-service:50051")

with grpc.insecure_channel(target) as channel:
    client = user_pb2_grpc.UserServiceStub(channel)
    response = client.GetUser(
        user_pb2.GetUserRequest(user_id="10001"),
        timeout=3,
    )
```

必须设置调用超时：

```python
timeout=3
```

禁止无限等待：

```python
response = client.GetUser(request)
```

推荐环境变量命名：

```text
USER_SERVICE_ADDR=user-service:50051
ORDER_SERVICE_ADDR=order-service:50051
PAYMENT_SERVICE_ADDR=payment-service:50051
```

---

## 10. Dockerfile 标准模板

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vendor/rpcdemo /app/rpcdemo

COPY app.py .

EXPOSE 50051 8080

CMD ["python", "/app/app.py"]
```

`EXPOSE` 只是镜像元数据，不会自动发布宿主机端口，也不会让容器加入 `rpc-network`。

---

## 11. Compose 标准模板

一个仓库部署一个服务时：

```yaml
services:
  inventory-service:
    build:
      context: .
      dockerfile: Dockerfile

    environment:
      GRPC_PORT: "50051"
      HTTP_PORT: "8080"
      PRODUCT_SERVICE_ADDR: product-service:50051

    expose:
      - "50051"
      - "8080"

    networks:
      rpc-network:
        aliases:
          - inventory-service

    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 10s

    restart: unless-stopped

networks:
  rpc-network:
    external: true
    name: rpc-network
```

关键点：

- `build` 继续使用仓库内的 Dockerfile。
- `expose` 不会占用宿主机端口。
- `external: true` 表示使用已有的 `rpc-network`。
- `aliases` 是其他服务使用的稳定调用名称。
- 不要设置 `container_name`，让 Dokploy 管理实际容器名称。

---

## 12. Dokploy 部署流程

### 12.1 新建项目

在 Dokploy 中选择：

```text
Create Service → Docker Compose
```

不要选择单个 Application，除非你准备在 Dokploy 高级设置中手工配置网络和 Alias。

### 12.2 Git 配置

```text
Source: GitHub
Repository: Shijf/rpc-example-service
Branch: main
Compose Path: ./compose.yaml
Compose Type: Docker Compose
```

### 12.3 网络与域名

- RPC 服务不需要配置 Domain。
- RPC 服务不需要发布宿主机端口。
- Compose 已经声明 `rpc-network`。
- 为避免额外网络干扰，当前示例不使用 Isolated Deployments。

### 12.4 Auto Deploy

推荐启用 GitHub Webhook/Auto Deploy：

```text
git push
  ↓
GitHub
  ↓ Webhook
Dokploy 拉取 main
  ↓
Dockerfile 构建
  ↓
Compose 更新容器
  ↓
健康检查
```

### 12.5 部署顺序

第一次部署两个互相依赖的服务时：

1. 先部署被调用服务。
2. 再部署调用服务。
3. 即使顺序相反，调用方也必须能容忍短暂 `UNAVAILABLE`。
4. 不要在启动阶段无限等待所有下游服务。

---

## 13. 健康检查与 Reflection

每个 RPC 服务至少提供两类健康能力。

### 13.1 Docker/Dokploy 健康检查

提供内部 HTTP 端点：

```text
GET /healthz
```

正常返回：

```json
{
  "status": "SERVING",
  "service": "inventory-service"
}
```

基础健康检查应该只判断本服务能否处理请求，不要因为一个非关键下游短暂失败就让本服务无限重启。

### 13.2 gRPC 标准健康服务

启用 `grpc.health.v1.Health`，供 gRPC 客户端或内部监控使用。

状态建议：

```text
SERVING
NOT_SERVING
```

### 13.3 gRPC Reflection

开发和内部调试环境可以启用 Reflection，方便 `grpcurl` 等工具发现接口。公开或高安全环境应评估是否需要关闭。

---

## 14. 超时、重试和幂等性

### 14.1 超时

每次 RPC 必须设置 deadline/timeout。

建议初始值：

| 调用类型 | 建议超时 |
|---|---|
| 普通查询 | 1–3 秒 |
| 内部写操作 | 3–5 秒 |
| 慢任务 | 不应同步等待，改异步任务 |

### 14.2 重试

只自动重试明确安全的操作：

- `Get*`
- `List*`
- 使用幂等键的写操作

不要无条件重试：

- 扣款
- 创建订单
- 扣库存
- 发送短信或邮件

否则可能重复执行。

### 14.3 幂等键

关键写接口建议带：

```protobuf
string idempotency_key = 1;
```

服务端保存处理结果，同一个幂等键重复请求时返回第一次结果。

---

## 15. 数据库边界

推荐原则：服务拥有自己的数据，其他服务通过 RPC 查询或操作，不直接读取对方数据库。

推荐：

```text
order-service
  ├─ order 数据库
  └─ 调用 user-service.GetUser()

user-service
  └─ user 数据库
```

不推荐：

```text
order-service 直接查询 user 数据库表
```

这样做的好处：

- 用户表结构可以独立演进。
- 权限和数据规则集中在用户服务。
- 订单服务不会依赖用户数据库的内部实现。
- 服务可以独立迁移数据库。

同一个 MySQL 服务器可以承载多个逻辑数据库，但必须：

- 每个服务使用独立数据库。
- 每个服务使用独立账号。
- 账号只拥有自身数据库权限。
- 密码通过 Dokploy 环境变量或 Secret 注入。

---

## 16. 安全规范

当前 `rpc-network` 是服务器内部加密 overlay 网络，RPC 端口不发布到宿主机。

最低要求：

1. 不发布内部 `50051`。
2. 不在 Git 中提交密码、Token 或私钥。
3. 密码通过 Dokploy Environment/Secret 配置。
4. 日志不得输出完整 Token、密码或敏感请求体。
5. 关键 RPC 必须验证调用者身份和业务权限。

当前示例使用：

```python
grpc.insecure_channel(...)
```

这里的 `insecure` 表示 gRPC 本身没有启用 TLS，不代表流量公开暴露。当前流量仅位于内部加密 overlay 网络。

以下情况应升级到应用层 TLS/mTLS：

- 多台不完全可信的服务器。
- 跨机房或跨云。
- 合规要求端到端加密。
- 需要验证服务身份。

---

## 17. 日志与可观测性

每个服务日志至少包含：

- 时间。
- 服务名称。
- RPC 方法。
- 请求 ID/Trace ID。
- 耗时。
- gRPC 状态码。
- 错误摘要。

建议格式：

```json
{
  "service": "order-service",
  "method": "CreateOrder",
  "request_id": "req-123",
  "elapsed_ms": 18.4,
  "grpc_code": "OK"
}
```

禁止默认记录：

- 密码。
- Access Token。
- 完整身份证号或银行卡号。
- 大段二进制内容。

服务增多后建议引入 OpenTelemetry，并统一收集 trace、metric 和 log。

---

## 18. 扩容与负载均衡

单机、单副本阶段，Docker DNS 已足够。

gRPC 使用长期 HTTP/2 连接。服务扩展为多个副本后，一个客户端连接可能长期停留在同一个副本，不能假设每个 RPC 都会被平均分配。

需要多副本时评估：

1. gRPC 客户端 DNS 解析和 round-robin。
2. Docker Swarm `tasks.<service>` 地址。
3. Envoy 等支持 gRPC 的内部代理。
4. 服务规模继续扩大后引入 Consul 或服务网格。

不要仅通过增加副本就假设 gRPC 请求已经均匀负载。

---

## 19. 测试方法

### 19.1 服务器浏览器测试

当前演示入口：

```text
http://user-service:8080/demo
http://order-service:8080/demo
```

### 19.2 Docker DNS 测试

```bash
docker exec server-browser getent hosts user-service order-service
```

应该返回 `rpc-network` 内部地址，例如：

```text
10.0.2.x user-service
10.0.2.x order-service
```

### 19.3 HTTP 健康检查

```bash
docker exec server-browser \
  curl -fsS http://user-service:8080/healthz
```

### 19.4 双向调用测试

```bash
docker exec server-browser \
  curl -fsS http://user-service:8080/demo

docker exec server-browser \
  curl -fsS http://order-service:8080/demo
```

### 19.5 检查端口是否误发布

```bash
docker ps --format '{{.Names}} {{.Ports}}'
```

安全的内部端口显示：

```text
50051/tcp, 8080/tcp
```

需要检查的宿主机映射：

```text
0.0.0.0:50051->50051/tcp
```

---

## 20. 常见故障排查

### 20.1 `UNAVAILABLE: failed to connect to all addresses`

检查：

1. 被调用服务是否运行且健康。
2. 两边是否都加入 `rpc-network`。
3. Network Alias 是否正确。
4. 服务是否监听 `0.0.0.0`/`[::]`，而不是 `127.0.0.1`。
5. 调用端口是否正确。

### 20.2 服务名解析到 `198.18.x.x`

这通常表示 Docker 网络中没有对应名称，查询继续落到了 Tailscale DNS。

检查：

```bash
docker network inspect rpc-network
```

确认服务存在且网络别名正确。

### 20.3 Dokploy 显示部署成功，但只有一个服务

如果一个仓库包含多个服务，却选择了 Dokploy Application，Dokploy 只会启动一个镜像进程。

解决方案：

- 一个仓库一个服务：Application 或 Compose 均可。
- 一个仓库多个服务：使用 Docker Compose。

### 20.4 服务中心暂时显示未启动

服务中心不是实时查询：

- 宿主机每 5 分钟生成状态。
- 浏览器每 2 分钟刷新页面。

最长可能有数分钟延迟。刷新后仍异常，再检查 Compose 标签和 Docker 状态。

### 20.5 容器名称带随机字符

这是 Dokploy 的正常行为：

```text
project-random-user-service-1
```

不要依赖实际容器名称。始终使用：

```text
user-service:50051
```

---

## 21. 新服务上线清单

创建新 RPC 服务时逐项确认：

### 接口

- [ ] Proto package 带版本，例如 `payment.v1`。
- [ ] Service 名称以 `Service` 结尾。
- [ ] Request/Response 使用独立消息。
- [ ] 没有修改已经发布的字段编号。
- [ ] 写接口考虑幂等键。

### 代码

- [ ] gRPC 监听 `0.0.0.0:50051` 或 `[::]:50051`。
- [ ] 每个下游调用设置 timeout。
- [ ] 只对幂等操作自动重试。
- [ ] 实现标准 gRPC Health。
- [ ] 提供 `/healthz`。
- [ ] 支持 SIGTERM 和优雅关闭。

### Docker

- [ ] Dockerfile 可独立构建。
- [ ] Compose 使用 `expose`，没有误用 `ports`。
- [ ] 加入外部 `rpc-network`。
- [ ] 设置唯一、稳定的 Network Alias。
- [ ] 没有设置 `container_name`。
- [ ] 健康检查可以通过。

### Dokploy

- [ ] 仓库和 `main` 分支正确。
- [ ] Compose Path 为 `./compose.yaml`。
- [ ] 密钥只保存在 Dokploy Environment/Secret。
- [ ] 没有给纯内部 RPC 服务配置公网 Domain。
- [ ] 部署日志没有循环重启。
- [ ] Auto Deploy/Webhook 按需开启。

### 验证

- [ ] Docker DNS 可以解析服务别名。
- [ ] `/healthz` 返回 200。
- [ ] gRPC 正常返回。
- [ ] 下游不可用时调用能在超时后结束。
- [ ] 宿主机没有暴露 `50051`。
- [ ] 服务中心状态正常。

---

## 22. 当前示例的学习路径

建议按以下顺序阅读：

1. 阅读 `rpc-contracts/proto/rpcdemo/v1/rpcdemo.proto`，理解唯一接口契约。
2. 阅读 User Service 的 `GetUser()` 服务端实现。
3. 阅读 Order Service 如何创建 `UserServiceStub`。
4. 阅读 Order Service 的 `ListOrders()` 服务端实现。
5. 阅读 User Service 如何创建 `OrderServiceStub`。
6. 阅读两个仓库的 `compose.yaml`，理解共享网络和别名。
7. 在其中一个仓库修改返回内容并推送。
8. 观察 GitHub Actions 和 Dokploy Auto Deploy。
9. 从服务器浏览器验证新版本。

最终应形成下面的日常开发习惯：

```text
先定义或修改 Proto
        ↓
实现服务端接口
        ↓
生成并调用客户端 Stub
        ↓
本地构建与测试
        ↓
Git Commit / Push
        ↓
Dokploy 自动部署
        ↓
健康检查与 RPC 验证
```

---

## 23. 后续演进建议

按优先级逐步建设：

已完成：

- 建立独立 `rpc-contracts` 仓库，消除 Proto 复制。
- 使用 Buf lint，并固定生成器版本。
- 自动生成并编译验证 Python、TypeScript、Go SDK。
- 两个现有 Python 服务改用固定版本的中央 SDK。

下一阶段按优先级逐步建设：

1. 在协议仓库的 CI 中加入相对 `main` 的 `buf breaking` 检查。
2. 统一请求 ID、错误模型、日志格式和鉴权 metadata。
3. 接入 OpenTelemetry 链路追踪。
4. 引入异步消息队列处理长任务和事件通知。
5. 多节点或跨机房后，再评估 Consul、Envoy 或服务网格。

当前阶段不需要为了“看起来完整”而过早安装复杂注册中心。先保持 Docker DNS、统一网络、稳定服务名和良好接口规范，已经能够支撑这台服务器上的内部微服务开发。

---

## 24. 中央 Contracts 与三语言 SDK 的日常流程

### 24.1 谁负责什么

```text
rpc-contracts     定义“有哪些接口、字段和类型”，生成三种语言代码
Docker DNS        把 user-service 等稳定名称解析为运行中的容器地址
gRPC              规定二进制消息和远程调用过程
业务仓库          实现接口，或通过生成客户端调用其他服务
Dokploy           根据各业务仓库独立构建、部署和回滚
```

SDK 不是单独运行的服务，也不负责服务发现。它是一组生成代码：包含消息类型、序列化逻辑、服务端基类和客户端 Stub。

### 24.2 修改接口

```bash
cd /home/shijf/rpc-contracts

# 1. 只修改 proto 下的源文件
vim proto/rpcdemo/v1/rpcdemo.proto

# 2. 统一校验并重新生成 Python、Node、Go
./scripts/generate.sh

# 3. 检查差异
git diff

# 4. 提交并打版本标签
git add .
git commit -m "feat: add payment rpc"
git tag v0.2.0
git push origin main --tags
```

已经发布的字段编号不能改动或复用。不兼容变更新建 `v2` 包，不直接破坏 `v1`。

### 24.3 升级现有 Python 服务

```bash
cd /home/shijf/rpc-contracts
./scripts/vendor-python.sh /home/shijf/rpc-user-service

cd /home/shijf/rpc-user-service
git diff
docker build -t rpc-user-service:contract-test .
git add .
git commit -m "chore: upgrade rpc contracts to 0.2.0"
git push origin main
```

`vendor/RPC_CONTRACTS_VERSION`、镜像环境变量和 OCI Label 会记录服务使用的契约版本，`/healthz` 也会返回它。

### 24.4 新建 Python、Node.js、Go 服务

- Python 导入：`from rpcdemo.v1 import rpcdemo_pb2, rpcdemo_pb2_grpc`
- Node.js 导入：`import { UserServiceClient } from "@shijf/rpc-contracts"`
- Go 导入：`github.com/Shijf/rpc-contracts/sdk/go/rpcdemo/v1`

无论使用哪种语言，容器都加入外部 `rpc-network`，调用地址继续写稳定名称，例如 `user-service:50051`。不要写容器 IP，也不要把 `50051` 发布到宿主机。

### 24.5 发布顺序

兼容变更的安全顺序是：先发布新版 contracts，再升级服务端，再逐个升级调用方。因为新增字段在 Proto3 中可以被旧客户端忽略，所以不需要让所有仓库同一秒部署。删除或改变已有字段属于破坏性变更，应使用新包版本并保留一段双版本迁移期。

---

## 25. 2026-09-06 实际落地与验收记录

本节记录已经在服务器上完成并验证的真实状态，不是待办方案。

### 25.1 仓库与版本

| 仓库 | 作用 | 本次落地提交 |
| --- | --- | --- |
| `Shijf/rpc-contracts` | 唯一 Proto 来源，生成 Python、Node.js、Go SDK | `a426ab8`，标签 `v0.1.0` |
| `Shijf/rpc-user-service` | 用户服务，同时演示调用订单服务 | `d4afacf` |
| `Shijf/rpc-order-service` | 订单服务，同时演示调用用户服务 | `fbdaf34` |
| `Shijf/rpc-platform` | 架构、部署和运维文档 | `f804161` |

服务器工作目录：

```text
/home/shijf/rpc-contracts
/home/shijf/rpc-user-service
/home/shijf/rpc-order-service
/home/shijf/rpc-platform
```

所有仓库使用服务器上的 GitHub 公共 SSH 身份配置，私钥不进入代码仓库、Docker 镜像或 Compose 文件。

### 25.2 已完成的改造

- `.proto` 只存在于 `rpc-contracts/proto/rpcdemo/v1/rpcdemo.proto`。
- Buf 同时生成 Python、Node.js/TypeScript、Go SDK，并固定生成器版本。
- Python SDK 可以构建为标准 Python 包。
- Node.js SDK 使用 `@grpc/grpc-js`，TypeScript 编译通过。
- Go SDK 是独立 Go module，`go test ./...` 通过。
- 两个 Python 服务删除了重复 Proto 和构建期 `grpcio-tools`。
- 两个服务携带经过验证的固定版本 SDK，Dokploy 构建不需要读取 GitHub 私钥。
- 镜像 Label、环境变量、`vendor/RPC_CONTRACTS_VERSION` 和 `/healthz` 都记录契约版本 `0.1.0`。
- `GetUser` 返回消息已按 Buf 标准命名为 `GetUserResponse`，字段编号和 RPC 方法路径保持兼容。

### 25.3 跨语言验收

在隔离 Docker 网络中完成过以下真实调用：

```text
Python user-service  ──gRPC──> Python order-service
Python order-service ──gRPC──> Python user-service
Node.js client       ──gRPC──> Python user-service
Go client            ──gRPC──> Python user-service
```

随后 Dokploy 自动重建了正式容器，正式环境验收结果：

- User Service 状态为 `healthy`。
- Order Service 状态为 `healthy`。
- User → Order 调用约 `4.26 ms`。
- Order → User 调用约 `4.20 ms`。
- 两个 `/healthz` 都返回 `rpc_contracts: 0.1.0`。
- 服务仍只通过 `rpc-network` 暴露内部 `50051`，没有新增宿主机端口。
- `rpc-contracts`、User Service、Order Service、RPC Platform 四个 GitHub Actions 均执行成功。
- 测试使用的临时容器、网络、镜像和依赖缓存已经清理。

### 25.4 随时复查正式环境

```bash
docker ps \
  --filter name=rpctest-userservice \
  --filter name=rpctest-orderservice

docker exec rpctest-userservice-4dyz9j-user-service-1 \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/healthz").read().decode())'

docker exec rpctest-orderservice-hsayiz-order-service-1 \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/healthz").read().decode())'
```

容器名称中的随机部分可能在 Dokploy 重新部署后改变。脚本或正式配置不要依赖完整容器名称；业务调用始终使用 `user-service:50051`、`order-service:50051` 等网络别名。

### 25.5 从演示进入真实项目

真实项目继续沿用同一套基础设施，但每个服务必须有明确的业务边界：

1. 先写业务需求和数据归属，不先按技术层随意拆服务。
2. 在 `rpc-contracts` 增加带版本的业务包，例如 `catalog.v1`、`payment.v1`。
3. 执行 `./scripts/generate.sh`，让三种语言 SDK 同时更新。
4. 服务仓库只实现自己拥有的接口和数据库，不直接读取其他服务的数据库。
5. Compose 加入外部 `rpc-network`，设置唯一稳定的网络别名。
6. 本地完成单元测试、镜像构建、健康检查和 RPC 集成测试。
7. 推送 GitHub，由现有 CI 和 Dokploy 完成构建部署。
8. 从服务器浏览器和服务中心验收，不为纯内部 RPC 服务开放公网域名。

这套结构已经具备真实项目开发条件；后续新增服务不需要重新安装“服务发现中心”，只需要复用 `rpc-network`、中央 contracts、SDK 和 Dokploy 部署规范。
