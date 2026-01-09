# StandX Maker Bot

双边挂单做市机器人，基于价格推送自动管理买卖挂单。

## 功能特性

- **双边挂单**：根据配置的距离在买卖两侧自动挂单
- **价格监控**：通过 WebSocket 实时接收价格推送
- **智能撤单**：价格靠近时自动撤单避免成交
- **波动率控制**：高波动时暂停挂单
- **持仓限制**：超过最大持仓自动停止做市
- **延迟监控**：记录 API 调用延迟

## 安装

```bash
pip install -r requirements.txt
```

## 配置

复制配置模板并填写钱包私钥：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
wallet:
  chain: bsc # bsc | solana
  private_key: "YOUR_PRIVATE_KEY_HERE"

symbol: BTC-USD

# 挂单参数
order_distance_bps: 10 # 挂单距离 last_price 的 bps
cancel_distance_bps: 5 # 价格靠近到这个距离时撤单（避免成交）
rebalance_distance_bps: 20 # 价格远离超过这个距离时撤单（重新挂更优价格）
order_size_btc: 0.01 # 单笔挂单大小

# 仓位控制
max_position_btc: 0.1 # 最大持仓，超过停止做市

# 波动率控制
volatility_window_sec: 5 # 观察窗口秒数
volatility_threshold_bps: 5 # 窗口内波动小于此值才允许挂单
```

## 运行

启动做市机器人：

```bash
python main.py
```

指定配置文件：

```bash
python main.py --config my_config.yaml
```

## 监控脚本

`monitor.py` 用于监控多个账户状态，支持余额告警和持仓告警。

```bash
# 监控多个账户
python monitor.py config.yaml config-bot2.yaml config-bot3.yaml

# 或使用 -c 参数
python monitor.py -c config.yaml -c config-bot2.yaml
```

### 通知服务配置

监控脚本支持通过 Telegram 发送告警通知。需要部署通知服务并配置环境变量：

1. 部署通知服务：https://github.com/frozen-cherry/tg-notify
2. 设置环境变量：

```bash
export NOTIFY_URL="http://your-server:8000/notify"
export NOTIFY_API_KEY="your-api-key"
```

Windows PowerShell:

```powershell
$env:NOTIFY_URL = "http://your-server:8000/notify"
$env:NOTIFY_API_KEY = "your-api-key"
```

## 延迟测试

`test_latency.py` 用于测试 API 调用延迟：

```bash
python test_latency.py
```

## 其他脚本

- `query_status.py`: 查询账户状态（余额、持仓、积分等）

## 注意事项

1. **私钥安全**：`config.yaml` 包含钱包私钥，请勿提交到公开仓库
2. **网络延迟**：建议在靠近交易所服务器的地区运行（如新加坡）
3. **做市风险**：做市策略有持仓风险，请谨慎设置 `max_position_btc`
4. **撤单策略**：程序退出时会自动撤销所有挂单
5. **邀请码说明**：本脚本默认使用作者的邀请码，您会获得 **5% boost**，作者也会获得推荐奖励。感谢您的支持！

## License

MIT
