# RPC 服务发现演示

这个项目通过 Dokploy 或 Docker Compose 部署两个服务：

- `user-service:50051`：提供 `UserService.GetUser`。
- `order-service:50051`：提供 `OrderService.ListOrders`。

两个服务通过 `rpc-network` 中的 Docker DNS 名称调用彼此，不使用容器 IP，也不向宿主机发布 RPC 端口。

## 演示入口

服务器浏览器加入 `rpc-network` 后可以打开：

- `http://user-service:8080/demo`：User Service 通过 gRPC 调用 Order Service。
- `http://order-service:8080/demo`：Order Service 通过 gRPC 调用 User Service。

HTTP 端口仅用于直观展示调用结果，业务通信发生在内部的 `50051` gRPC 端口。

## Dokploy 部署

1. 在 Dokploy 新建项目和 Docker Compose 服务。
2. Source Type 选择 GitHub、GitLab、Gitea 或 Git。
3. 选择本仓库与 `main` 分支。
4. Compose Path 设置为 `./compose.yaml`。
5. 不需要添加 Domain；两个演示 HTTP 页面只供服务器浏览器访问。
6. 保存后部署，并根据需要打开 Auto Deploy/Webhook。

服务器需要预先存在公共网络：

```bash
docker network create --driver overlay --attachable --opt encrypted rpc-network
```

## 本地手动部署

```bash
./deploy.sh
```

## 接口变更

修改 `proto/rpcdemo.proto`，重新构建镜像并运行 `./deploy.sh`。

## 卸载

运行 `./uninstall.sh`。共享的 `rpc-network` 与源码目录会保留，避免影响其他 RPC 服务。
