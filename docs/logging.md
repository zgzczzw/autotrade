# AutoTrade 日志系统文档

## 日志文件位置

所有日志文件位于项目根目录的 `logs/` 文件夹下：

```
logs/
├── launcher.log              # 启动脚本日志
├── autotrade.log             # 主应用日志（INFO及以上）
├── autotrade.error.log       # 错误日志（ERROR及以上）
├── autotrade.debug.log       # 调试日志（仅 DEBUG 级别）
├── autotrade.2024-01-01.log  # 历史日志（按天轮转）
└── access.log                # HTTP 访问日志
```

## 日志分类说明

### 1. 启动脚本日志 (`launcher.log`)

记录 `python3 start.py` 启动过程中的所有操作：
- 服务启动/停止
- 进程管理
- 错误信息

查看方式：
```bash
tail -f logs/launcher.log
```

### 2. 主应用日志 (`autotrade.log`)

记录后端应用的主要运行信息：
- 服务启动/关闭
- 策略执行
- 回测进度
- 数据库操作
- 一般信息

查看方式：
```bash
tail -f logs/autotrade.log
```

### 3. 错误日志 (`autotrade.error.log`)

仅记录错误级别及以上的日志：
- 异常堆栈
- 错误信息
- 详细位置（文件名、函数名、行号）

查看方式：
```bash
tail -f logs/autotrade.error.log
```

### 4. 调试日志 (`autotrade.debug.log`)

仅在 `LOG_LEVEL=DEBUG` 时生成，包含：
- 详细的调试信息
- SQL 查询
- API 请求/响应详情

查看方式：
```bash
tail -f logs/autotrade.debug.log
```

### 5. 访问日志 (`access.log`)

记录所有 HTTP 请求：
```
2024-01-01 12:00:00 [INFO] autotrade.access: 127.0.0.1 - "GET /api/strategies HTTP/1.1" 200 - 0.023s
```

格式：
```
时间 [级别] 日志器: 客户端IP - "方法 路径 协议" 状态码 - 处理时间
```

查看方式：
```bash
tail -f logs/access.log
```

## 日志级别

从低到高：
1. **DEBUG** - 调试信息，仅在开发使用
2. **INFO** - 一般信息，默认级别
3. **WARNING** - 警告信息
4. **ERROR** - 错误信息
5. **CRITICAL** - 严重错误

## 配置方式

编辑 `backend/.env` 文件：

```bash
# 日志级别
LOG_LEVEL=INFO

# 日志格式: text 或 json
LOG_FORMAT=text

# 日志文件大小限制（MB）
LOG_MAX_BYTES=10

# 保留的日志文件数量
LOG_BACKUP_COUNT=10

# 是否输出到控制台
LOG_CONSOLE=true
```

修改配置后需要重启服务生效。

## 前端日志

前端日志通过 API 发送到后端记录：
- 开发环境：输出到浏览器控制台
- 生产环境：错误日志发送到后端，记录在 `autotrade.log` 中

前端日志格式：
```
[Frontend] 错误消息 - {"url": "...", "user_agent": "...", "data": {...}}
```

## 日志轮转

### 按时间轮转
- `autotrade.log` - 每天午夜自动轮转
- 保留最近 30 天的日志

### 按大小轮转
- `autotrade.error.log` - 达到 10MB 自动轮转
- 保留最近 10 个文件

### 手动清理
```bash
# 查看日志目录大小
du -sh logs/

# 清理 7 天前的日志
find logs/ -name "*.log.*" -mtime +7 -delete

# 清空当前日志（不推荐，除非磁盘空间不足）
> logs/autotrade.log
```

## 故障排查

### 查看实时日志
```bash
# 所有日志
tail -f logs/*.log

# 仅错误
tail -f logs/autotrade.error.log

# 过滤特定关键词
tail -f logs/autotrade.log | grep "策略"
```

### 查找特定时间段的日志
```bash
# 今天的错误
grep "2024-01-01" logs/autotrade.error.log

# 特定策略的日志
grep "strategy_id=1" logs/autotrade.log
```

### 统计错误数量
```bash
# 今日错误数
grep "$(date +%Y-%m-%d)" logs/autotrade.error.log | wc -l

# 各类型错误统计
grep "ERROR" logs/autotrade.log | cut -d']' -f3 | sort | uniq -c
```

## 最佳实践

1. **生产环境**
   - 设置 `LOG_LEVEL=INFO`
   - 设置 `LOG_FORMAT=json`（便于日志分析工具处理）
   - 定期归档历史日志

2. **开发环境**
   - 设置 `LOG_LEVEL=DEBUG`
   - 设置 `LOG_FORMAT=text`
   - 开启控制台输出

3. **排查问题**
   - 先查看 `autotrade.error.log`
   - 结合 `access.log` 查看请求上下文
   - 必要时开启 DEBUG 级别

4. **监控告警**
   - 监控 `autotrade.error.log` 的增长速度
   - 设置错误数量阈值告警
