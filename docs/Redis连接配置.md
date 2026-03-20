# Redis 连接配置

## 概述

本文档提供 WeKnora 本地开发环境中 Redis 的完整连接配置信息，供其它应用直连使用。

## 连接信息

### 基础配置
- **Host**：`172.16.100.211`（你的机器 IP）或 `localhost`（本机）
- **Port**：`6379`
- **Password**：`redis123!@#`
- **Database**：`0`
- **版本**：Redis 7.0.15

### 标准 URL 格式
```
redis://[<username>:<password>@]<host>:<port>/<db>
```

### 你的实际连接串
```
redis://:redis123!@#@172.16.100.211:6379/0
```

> **说明**：
> - **用户名**：空（未启用 ACL 用户）
> - **密码**：`redis123!@#`
> - **Host**：`172.16.100.211`（你的机器 IP）
> - **Port**：`6379`
> - **DB**：`0`

## 各语言连接示例

### Python
```python
import redis

# 方式1：使用 URL + 密码分开（推荐）
r = redis.Redis.from_url(
    'redis://172.16.100.211:6379/0',
    password='redis123!@#'
)

# 方式2：直接传参
r = redis.Redis(
    host='172.16.100.211',
    port=6379,
    password='redis123!@#',
    db=0,
    decode_responses=True
)

# 测试连接
print(r.ping())
```

### Node.js
```js
const redis = require('redis');

// 方式1：URL + 密码分开（推荐）
const client = redis.createClient({
  url: 'redis://172.16.100.211:6379/0',
  password: 'redis123!@#'
});

// 方式2：直接传参
const client = redis.createClient({
  host: '172.16.100.211',
  port: 6379,
  password: 'redis123!@#',
  db: 0
});

client.on('connect', () => console.log('Redis connected'));
client.on('error', (err) => console.error('Redis Error', err));

await client.connect();
```

### Go
```go
import (
    "context"
    "log"
    "github.com/go-redis/redis/v8"
)

rdb := redis.NewClient(&redis.Options{
    Addr:     "172.16.100.211:6379",
    Password: "redis123!@#",
    DB:       0,
})

ctx := context.Background()
if err := rdb.Ping(ctx).Err(); err != nil {
    log.Fatal(err)
}
```

### Java (Jedis)
```java
import redis.clients.jedis.Jedis;

// 方式1：URL + 密码分开
Jedis jedis = new Jedis("172.16.100.211", 6379);
jedis.auth("redis123!@#");

// 方式2：使用连接字符串
String url = "redis://:redis123!@#@172.16.100.211:6379/0";
Jedis jedis = new Jedis(url);
```

### PHP
```php
<?php
$redis = new Redis();
$redis->connect('172.16.100.211', 6379);
$redis->auth('redis123!@#');
$redis->select(0);

// 测试
echo $redis->ping(); // PONG
?>
```

## 连接验证

### 命令行验证
```bash
# 基本连接测试
redis-cli -h 172.16.100.211 -p 6379 -a redis123!@# ping

# 查看服务信息
redis-cli -h 172.16.100.211 -p 6379 -a redis123!@# info server

# 查看内存使用
redis-cli -h 172.16.100.211 -p 6379 -a redis123!@# info memory
```

### 程序验证
所有语言的示例代码都包含连接测试，运行后应返回成功响应。

## 安全建议

1. **密码安全**：避免在代码中硬编码密码，建议使用环境变量或配置文件
2. **网络安全**：如果需要跨机器访问，确保防火墙开放 6379 端口
3. **连接池**：生产环境建议使用连接池管理 Redis 连接

## 环境变量配置

如果其它应用需要通过环境变量配置 Redis，可以使用：

```bash
REDIS_URL=redis://172.16.100.211:6379/0
REDIS_PASSWORD=redis123!@#
REDIS_HOST=172.16.100.211
REDIS_PORT=6379
REDIS_DB=0
```

## 故障排查

### 常见错误
- **连接超时**：检查网络和防火墙设置
- **认证失败**：确认密码 `redis123!@#` 正确
- **端口占用**：确认 6379 端口未被其他服务占用

### 诊断命令
```bash
# 检查 Redis 服务状态
docker-compose ps redis

# 查看 Redis 日志
docker-compose logs redis

# 测试网络连通性
telnet 172.16.100.211 6379
```

---

**状态**：Redis 已验证可用，配置信息如上。其它应用可以直接用这些连接串访问你的 Redis 实例。
