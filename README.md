# 🤖 Mobile-Use v2.0

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

> **AI-Driven Mobile Device Automation System** - 通过自然语言控制Android和iOS设备的智能自动化平台

## 🎯 项目概述

Mobile-Use v2.0 是一个基于大语言模型(LLM)的移动设备自动化系统，专为软件创新大赛设计。它能够理解自然语言指令，智能识别移动设备UI元素，并执行复杂的自动化任务。

### ✨ 核心特性

- 🧠 **AI驱动**: 集成多种LLM(OpenAI、Gemini、Claude、本地模型)
- 📱 **跨平台支持**: 统一控制Android和iOS设备
- 🎯 **智能UI识别**: 基于计算机视觉和AI的元素识别
- 🔄 **自动化工作流**: 复杂任务的智能分解和执行
- 🛡️ **错误恢复**: 智能错误检测和自动恢复机制
- 🔌 **插件系统**: 可扩展的第三方插件支持
- 🌐 **多界面**: CLI、Web界面和REST API

## 🏗️ 架构设计

```
┌─────────────────────────────────────┐
│        Presentation Layer           │  ← CLI/Web/API
├─────────────────────────────────────┤
│         Application Layer           │  ← Use Cases & DTOs
├─────────────────────────────────────┤
│          Domain Layer               │  ← Business Logic
├─────────────────────────────────────┤
│        Infrastructure Layer         │  ← External Services
└─────────────────────────────────────┘
```

### 🤖 AI代理系统

- **TaskPlannerAgent**: 任务规划和分解
- **ContextAnalyzerAgent**: 屏幕上下文分析
- **ActionExecutorAgent**: 设备操作执行
- **ResultValidatorAgent**: 结果验证和反馈

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Android Debug Bridge (ADB) - 用于Android设备
- iOS Device Bridge (idb) - 用于iOS设备
- 至少一个LLM API密钥

### 安装

```bash
# 克隆项目
git clone https://github.com/mobile-use/mobile-use-v2.git
cd mobile-use-v2

# 安装依赖 (推荐使用Poetry)
poetry install

# 或使用pip
pip install -e .
```

### 配置

```bash
# 复制配置模板
cp config/config.example.yaml config/config.yaml

# 编辑配置文件，添加LLM API密钥
vim config/config.yaml
```

### 基本使用

```bash
# 查看帮助
mobile-use --help

# 连接设备
mobile-use device connect

# 执行自动化任务
mobile-use run "打开微信，发送消息给张三：今天开会"

# 启动Web界面
mobile-use web --port 8080

# 查看执行日志
mobile-use logs --tail -f
```

## 📖 使用示例

### CLI命令示例

```bash
# 简单操作
mobile-use run "点击屏幕中央"
mobile-use run "向下滑动页面"
mobile-use run "输入文本：Hello World"

# 复杂任务
mobile-use run "打开淘宝，搜索iPhone 15，查看前三个商品的价格"
mobile-use run "打开微博，发布一条动态：今天天气真好"
mobile-use run "打开设置，开启飞行模式，等待5秒后关闭"

# 数据抓取
mobile-use extract "抓取当前页面的所有商品信息" --format json
mobile-use extract "获取联系人列表" --output contacts.csv
```

### Python API示例

```python
import asyncio
from mobile_use import MobileUseClient

async def main():
    # 创建客户端
    client = MobileUseClient()
    
    # 连接设备
    await client.connect_device("android")
    
    # 执行任务
    result = await client.execute_task(
        "打开微信，发送消息给张三：会议延期到明天"
    )
    
    print(f"任务结果: {result.success}")
    print(f"执行步骤: {result.steps}")

if __name__ == "__main__":
    asyncio.run(main())
```

## 🔧 配置说明

### LLM配置

```yaml
llm:
  providers:
    openai:
      model: "gpt-4-vision-preview"
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"
    
    gemini:
      model: "gemini-pro-vision"
      api_key: "${GOOGLE_API_KEY}"
    
    local:
      model: "llava:13b"
      base_url: "http://localhost:11434"
```

### 设备配置

```yaml
device:
  android:
    adb_host: "localhost"
    adb_port: 5037
    default_timeout: 30
  
  ios:
    idb_host: "localhost"
    idb_port: 10882
    default_timeout: 30
```

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 生成覆盖率报告
pytest --cov=mobile_use --cov-report=html
```

## 📚 文档

- [架构设计](docs/ARCHITECTURE.md)
- [API参考](docs/API_REFERENCE.md)
- [部署指南](docs/DEPLOYMENT.md)
- [插件开发](docs/PLUGIN_DEVELOPMENT.md)
- [故障排除](docs/TROUBLESHOOTING.md)

## 🤝 贡献

我们欢迎所有形式的贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细信息。

### 开发环境设置

```bash
# 安装开发依赖
poetry install --with dev

# 安装pre-commit钩子
pre-commit install

# 运行代码检查
make lint

# 运行测试
make test
```

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🏆 致谢

- 感谢所有贡献者的努力
- 特别感谢开源社区的支持
- 本项目为软件创新大赛参赛作品

## 📞 联系我们

- 项目主页: https://github.com/mobile-use/mobile-use-v2
- 问题反馈: https://github.com/mobile-use/mobile-use-v2/issues
- 邮箱: team@mobile-use.com

---

**🚀 让AI为你的移动设备自动化赋能！**
