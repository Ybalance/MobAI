"""OpenAI LLM provider implementation."""

import base64
import logging
from typing import Any

import httpx

from mobile_use.infrastructure.llm.base import (
    BaseLLMProvider,
    LLMConfig,
    LLMMessage,
    LLMResponse,
)

# 配置日志
logger = logging.getLogger("mobile_use.llm")
logger.setLevel(logging.INFO)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider implementation.

    Supports GPT-4, GPT-4 Vision, and other OpenAI models.
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Any = None

    async def initialize(self) -> None:
        """Initialize OpenAI client."""
        try:
            from openai import AsyncOpenAI

            # 配置超时：连接超时60秒，读取超时使用配置值（大模型需要更长时间）
            timeout = httpx.Timeout(
                connect=60.0,  # 连接超时60秒
                read=float(self.config.timeout),  # 读取超时使用配置值
                write=60.0,  # 写入超时60秒
                pool=60.0  # 连接池超时60秒
            )
            
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=timeout,
                max_retries=self.config.retry_attempts  # 使用配置的重试次数
            )
            self._initialized = True
            logger.info(f"[OpenAI] 初始化成功，模型: {self.config.model}, 读取超时: {self.config.timeout}秒")
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. "
                "Install with: pip install openai"
            )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any
    ) -> str:
        """Generate text from prompt using OpenAI."""
        if not self._initialized:
            await self.initialize()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        print(f"\n{'='*80}")
        print(f"🤖 [AI决策] 模型: {self.config.model}")
        print(f"📝 [AI输入] Prompt长度: {len(prompt)}字符")
        if len(prompt) <= 500:
            print(f"📝 [AI输入] 完整内容:\n{prompt}")
        else:
            print(f"📝 [AI输入] 内容预览:\n{prompt[:500]}...\n[内容过长，已截断]")
        print("⏳ [AI思考] 正在分析当前情况并制定执行策略...")
        
        response = await self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            **self.config.extra_params
        )

        content = response.choices[0].message.content or ""
        print(f"💭 [AI决策] 响应长度: {len(content)}字符")
        if len(content) <= 1000:
            print(f"🎯 [AI理由] 完整决策过程:\n{content}")
        else:
            print(f"🎯 [AI理由] 决策摘要:\n{content[:1000]}...\n[完整内容过长，已截断]")
        print(f"{'='*80}\n")
        
        # 保持原有的logger输出用于调试
        logger.info(f"[LLM请求] 模型: {self.config.model}, Prompt长度: {len(prompt)}")
        logger.info(f"[LLM响应] 响应长度: {len(content)}")
        
        return content

    async def chat(
        self,
        messages: list[LLMMessage],
        **kwargs: Any
    ) -> LLMResponse:
        """Send chat conversation to OpenAI."""
        if not self._initialized:
            await self.initialize()

        formatted_messages = []
        for msg in messages:
            if msg.images:
                # Vision model message with images
                content: list[dict[str, Any]] = [{"type": "text", "text": msg.content}]
                for image in msg.images:
                    b64_image = base64.b64encode(image).decode("utf-8")
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}"
                        }
                    })
                formatted_messages.append({
                    "role": msg.role,
                    "content": content
                })
            else:
                formatted_messages.append(msg.to_dict())

        logger.info(f"\n{'='*50}")
        logger.info(f"[LLM Chat] 模型: {self.config.model}, 消息数: {len(formatted_messages)}")
        
        response = await self._client.chat.completions.create(
            model=self.config.model,
            messages=formatted_messages,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            **self.config.extra_params
        )

        choice = response.choices[0]
        usage = response.usage
        
        content = choice.message.content or ""
        logger.info(f"[LLM响应] {content[:500]}..." if len(content) > 500 else f"[LLM响应] {content}")
        if usage:
            logger.info(f"[Token用量] prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")
        logger.info(f"{'='*50}\n")

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider="openai",
            usage={
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0
            },
            finish_reason=choice.finish_reason,
            raw_response=response
        )

    async def analyze_image(
        self,
        image: bytes,
        prompt: str,
        **kwargs: Any
    ) -> str:
        """Analyze image using vision-capable model."""
        if not self._initialized:
            await self.initialize()

        # 使用当前配置的模型，大多数现代模型都支持图片
        model = self.config.model
        image_size_kb = len(image) / 1024
        
        print(f"\n{'='*80}")
        print(f"👁️ [AI视觉] 模型: {model}")
        print(f"🖼️ [AI视觉] 图片大小: {image_size_kb:.1f}KB")
        print(f"📝 [AI视觉] 分析任务: {prompt[:200]}..." if len(prompt) > 200 else f"📝 [AI视觉] 分析任务: {prompt}")
        print("🔍 [AI视觉] 正在分析屏幕截图，识别UI元素和当前状态...")
        
        b64_image = base64.b64encode(image).decode("utf-8")

        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_image}",
                                "detail": kwargs.get("detail", "auto")
                            }
                        }
                    ]
                }
            ],
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens or 4096),
            **self.config.extra_params
        )

        content = response.choices[0].message.content or ""
        print(f"🎯 [AI视觉] 分析完成，响应长度: {len(content)}字符")
        if len(content) <= 800:
            print(f"📊 [AI视觉] 分析结果:\n{content}")
        else:
            print(f"📊 [AI视觉] 分析摘要:\n{content[:800]}...\n[完整内容过长，已截断]")
        print(f"{'='*80}\n")
        
        return content

    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None
            self._initialized = False
