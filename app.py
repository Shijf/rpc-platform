#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
from concurrent import futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

import rpcdemo_pb2
import rpcdemo_pb2_grpc


ROLE = os.environ.get("ROLE", "user")
GRPC_PORT = int(os.environ.get("GRPC_PORT", "50051"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8080"))
USER_SERVICE_ADDR = os.environ.get("USER_SERVICE_ADDR", "user-service:50051")
ORDER_SERVICE_ADDR = os.environ.get("ORDER_SERVICE_ADDR", "order-service:50051")
HOSTNAME = socket.gethostname()


class UserService(rpcdemo_pb2_grpc.UserServiceServicer):
    def GetUser(self, request, context):
        user_id = request.user_id or "10001"
        return rpcdemo_pb2.User(
            user_id=user_id,
            nickname=f"演示用户-{user_id}",
            source_service=f"user-service/{HOSTNAME}",
        )


class OrderService(rpcdemo_pb2_grpc.OrderServiceServicer):
    def ListOrders(self, request, context):
        user_id = request.user_id or "10001"
        return rpcdemo_pb2.ListOrdersResponse(
            user_id=user_id,
            source_service=f"order-service/{HOSTNAME}",
            orders=[
                rpcdemo_pb2.Order(order_id="ORD-2026-001", product_name="机械键盘", amount_cents=69900),
                rpcdemo_pb2.Order(order_id="ORD-2026-002", product_name="显示器支架", amount_cents=32900),
            ],
        )


def call_remote() -> dict:
    started = time.perf_counter()
    if ROLE == "user":
        target = ORDER_SERVICE_ADDR
        with grpc.insecure_channel(target) as channel:
            stub = rpcdemo_pb2_grpc.OrderServiceStub(channel)
            response = stub.ListOrders(
                rpcdemo_pb2.ListOrdersRequest(user_id="10001"), timeout=3
            )
        payload = {
            "flow": "user-service → order-service",
            "target": target,
            "response": {
                "user_id": response.user_id,
                "orders": [
                    {
                        "order_id": item.order_id,
                        "product_name": item.product_name,
                        "amount_cents": item.amount_cents,
                    }
                    for item in response.orders
                ],
                "source_service": response.source_service,
            },
        }
    else:
        target = USER_SERVICE_ADDR
        with grpc.insecure_channel(target) as channel:
            stub = rpcdemo_pb2_grpc.UserServiceStub(channel)
            response = stub.GetUser(rpcdemo_pb2.GetUserRequest(user_id="10001"), timeout=3)
        payload = {
            "flow": "order-service → user-service",
            "target": target,
            "response": {
                "user_id": response.user_id,
                "nickname": response.nickname,
                "source_service": response.source_service,
            },
        }
    payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return payload


class DemoHandler(BaseHTTPRequestHandler):
    def send_json(self, status: int, body: dict):
        data = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "SERVING", "service": f"{ROLE}-service"})
            return
        if self.path in ("/", "/demo"):
            try:
                result = call_remote()
                self.send_json(
                    200,
                    {
                        "success": True,
                        "message": "Docker DNS 服务发现和双向 gRPC 调用正常",
                        "current_service": f"{ROLE}-service",
                        "current_container": HOSTNAME,
                        **result,
                    },
                )
            except grpc.RpcError as exc:
                self.send_json(
                    503,
                    {
                        "success": False,
                        "current_service": f"{ROLE}-service",
                        "grpc_code": exc.code().name,
                        "details": exc.details(),
                    },
                )
            return
        self.send_json(404, {"error": "not found", "available": ["/", "/demo", "/healthz"]})

    def log_message(self, fmt, *args):
        print(f"http {self.address_string()} {fmt % args}", flush=True)


def run_grpc(stop_event: threading.Event):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service_names = [reflection.SERVICE_NAME, health.SERVICE_NAME]
    if ROLE == "user":
        rpcdemo_pb2_grpc.add_UserServiceServicer_to_server(UserService(), server)
        service_names.append(rpcdemo_pb2.DESCRIPTOR.services_by_name["UserService"].full_name)
    else:
        rpcdemo_pb2_grpc.add_OrderServiceServicer_to_server(OrderService(), server)
        service_names.append(rpcdemo_pb2.DESCRIPTOR.services_by_name["OrderService"].full_name)

    health_service = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    health_service.set("", health_pb2.HealthCheckResponse.SERVING)
    for service_name in service_names:
        health_service.set(service_name, health_pb2.HealthCheckResponse.SERVING)
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    print(f"{ROLE}-service gRPC listening on {GRPC_PORT}", flush=True)
    stop_event.wait()
    health_service.enter_graceful_shutdown()
    server.stop(grace=5).wait()


def main():
    stop_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())

    grpc_thread = threading.Thread(target=run_grpc, args=(stop_event,), daemon=True)
    grpc_thread.start()

    httpd = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), DemoHandler)
    httpd.timeout = 0.5
    print(f"{ROLE}-service demo HTTP listening on {HTTP_PORT}", flush=True)
    while not stop_event.is_set():
        httpd.handle_request()
    httpd.server_close()


if __name__ == "__main__":
    main()
