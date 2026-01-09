# StandX Maker Bot

StandX Maker Points 活动的双边挂单做市机器人。在 mark price 两侧挂限价单获取积分，价格靠近时自动撤单避免成交。

**作者**: [@frozenraspberry](https://x.com/frozenraspberry)

## 策略原理

StandX 的 Maker Points 活动奖励挂单行为：订单在盘口停留超过 3 秒即可获得积分，无需成交。本机器人通过：

1. 在 mark price 两侧按配置距离挂买卖单
2. 实时监控价格，价格靠近时撤单避免成交
3. 价格远离时重新挂单到更优位置
4. 高波动时暂停挂单，等待市场稳定

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

# 挂单参数（bps = 0.01%，即 10 bps = 0.1%）
order_distance_bps: 20 # 挂单距离 mark_price 的 bps
cancel_distance_bps: 10 # 价格靠近到这个距离时撤单（避免成交）
rebalance_distance_bps: 30 # 价格远离超过这个距离时撤单（重新挂更优价格）
order_size_btc: 0.01 # 单笔挂单大小

# 仓位控制
max_position_btc: 0.1 # 最大持仓（绝对值），超过停止做市

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

## 日志文件

程序运行时会生成以下日志文件（已在 `.gitignore` 中排除）：

| 文件                   | 说明                                           |
| ---------------------- | ---------------------------------------------- |
| `latency_<config>.log` | API 调用延迟记录，格式：`时间戳,接口,延迟毫秒` |
| `status.log`           | 监控脚本的账户状态快照                         |

## 其他工具

### 监控脚本（可选）

`monitor.py` 用于监控多个账户状态，支持余额告警和持仓告警。独立于做市机器人运行。需要先行配置 tg-notify 通知服务。

```bash
python monitor.py config.yaml config-bot2.yaml config-bot3.yaml
```

通知服务配置：

1. 部署通知服务：https://github.com/frozen-cherry/tg-notify
2. 复制并编辑配置文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件填入你的通知服务地址和 API Key。

### 延迟测试

```bash
python test_latency.py
```

### 状态查询

```bash
python query_status.py
```

## 注意事项

1. **私钥安全**：`config.yaml` 包含钱包私钥，请勿提交到公开仓库
2. **网络延迟**：建议在延迟较低的服务器上运行,可通过 `test_latency.py` 测试
3. **做市风险**：做市策略有持仓风险，请谨慎设置 `max_position_btc`
4. **撤单策略**：程序退出时会自动撤销所有挂单

## 风险提示

- 本策略仅供学习和研究使用
- 加密货币交易存在高风险，可能导致资金损失
- 使用前请充分了解策略逻辑和风险
- 建议先以少量资金测试
- **作者不对使用本策略造成的任何损失负责**

## 邀请码

本脚本默认使用作者的邀请码，您会获得 **5% 积分加成**，作者也会获得推荐奖励。感谢支持！

## 许可证

MIT License

使用本项目时请标明作者 Twitter: [@frozenraspberry](https://x.com/frozenraspberry)

---

免责声明：本软件仅供学习和研究使用。使用本软件进行交易的所有风险由使用者自行承担。作者不对任何交易损失负责。
