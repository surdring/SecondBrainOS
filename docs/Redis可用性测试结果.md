# Redis 可用性测试结果（本地开发环境）

## 测试目的
验证当前 WeKnora 本地开发环境中 Redis 的：

- 容器运行状态
- 端口映射与宿主机连通性
- 密码鉴权
- 基础读写能力（SET/GET/DEL）

## 测试环境与关键配置
- Redis 容器名：`WeKnora-redis-dev`
- Redis 宿主机端口：`6379`
- Redis 密码：`.env` 中 `REDIS_PASSWORD=redis123!@#`
- Redis DB：`.env` 中 `REDIS_DB=0`

## 测试步骤与结果

### 1. 检查容器状态与端口映射
命令：

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'WeKnora-redis-dev|redis'
```

输出：

```text
WeKnora-redis-dev       Up 7 days              0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp
```

结论：

- 容器处于运行状态（`Up`）
- 端口已正确映射到宿主机（`6379->6379`）

### 2. 容器内鉴权与连通测试（PING）
命令：

```bash
docker exec -it WeKnora-redis-dev redis-cli -a 'redis123!@#' PING
```

输出：

```text
Warning: Using a password with '-a' or '-u' option on the command line interface may not be safe.
PONG
```

结论：

- 密码鉴权成功
- Redis 服务可达并正常响应（`PONG`）

### 3. 容器内读写测试（SELECT/SET/GET/DEL）
命令：

```bash
docker exec -i WeKnora-redis-dev redis-cli -a 'redis123!@#' <<'EOF'
SELECT 0
SET weknora:redis_smoke_test "ok" EX 60
GET weknora:redis_smoke_test
DEL weknora:redis_smoke_test
EOF
```

输出：

```text
Warning: Using a password with '-a' or '-u' option on the command line interface may not be safe.
OK
OK
ok
1
```

结论：

- `SELECT 0` 成功
- `SET` 成功返回 `OK`
- `GET` 返回值为 `ok`
- `DEL` 成功删除（返回 `1`）

### 4. 宿主机直连测试（PING）
命令：

```bash
redis-cli -h 127.0.0.1 -p 6379 -a 'redis123!@#' PING
```

输出：

```text
Warning: Using a password with '-a' or '-u' option on the command line interface may not be safe.
PONG
```

结论：

- 宿主机可通过 `127.0.0.1:6379` 访问 Redis
- 密码鉴权成功

## 总体结论
当前项目 Redis 在本地开发环境中可用：

- Redis 容器运行正常
- 端口映射与宿主机连通正常
- 密码鉴权正确
- 基础读写操作正常

## 安全提示
Redis 客户端提示 `-a` 直接在命令行传密码不安全：

- 该方式可能会在 shell 历史或进程列表中暴露密码
- 建议临时测试场景可接受；更严格的场景可使用环境变量或交互式方式输入
