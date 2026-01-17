"""Web API for Mobile-Use - 网页控制手机."""

import asyncio
import base64
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 配置日志输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))

from mobile_use.domain.entities.device import Device, DevicePlatform
from mobile_use.domain.value_objects.point import Point
from mobile_use.infrastructure.devices.android_controller import AndroidController
from mobile_use.infrastructure.llm.base import LLMConfig, LLMProviderType
from mobile_use.infrastructure.llm.openai_provider import OpenAIProvider
from mobile_use.domain.services.agents.orchestrator import AgentOrchestrator
from mobile_use.domain.services.agents.task_planner import TaskPlannerAgent
from mobile_use.domain.services.agents.context_analyzer import ContextAnalyzerAgent
from mobile_use.domain.services.agents.action_executor import ActionExecutorAgent
from mobile_use.domain.services.agents.result_validator import ResultValidatorAgent


# 全局设备控制器和AI组件
device_controller: AndroidController | None = None
llm_provider: OpenAIProvider | None = None
orchestrator: AgentOrchestrator | None = None
connected_websockets: list[WebSocket] = []

# 任务进度跟踪
task_progress: dict = {
    "running": False,
    "current_step": 0,
    "total_steps": 0,
    "current_action": "",
    "steps": [],
    "completed_steps": [],  # 已完成的步骤列表
    "status": "idle",  # idle, planning, executing, completed, failed, stopped
    "stop_requested": False  # 停止请求标志
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理."""
    global device_controller
    print("[Web] 启动Mobile-Use Web控制台...")
    yield
    if device_controller:
        await device_controller.disconnect()
        print("[Web] 已断开设备连接")


app = FastAPI(
    title="Mobile-Use Web Console",
    description="通过网页控制手机",
    version="2.0.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求模型
class ConnectRequest(BaseModel):
    device_id: str = "emulator-5554"


class TapRequest(BaseModel):
    x: int
    y: int


class SwipeRequest(BaseModel):
    direction: str  # up, down, left, right


class InputRequest(BaseModel):
    text: str


class CommandRequest(BaseModel):
    command: str
    params: dict = {}


# API路由
@app.get("/", response_class=HTMLResponse)
async def index():
    """返回Web控制台页面."""
    return get_html_page()


@app.post("/api/connect")
async def connect_device(request: ConnectRequest):
    """连接设备."""
    global device_controller

    try:
        if device_controller:
            await device_controller.disconnect()

        device = Device(
            device_id=request.device_id,
            platform=DevicePlatform.ANDROID,
            name="Android Device"
        )
        device_controller = AndroidController(device)
        await device_controller.connect()

        screen = device.screen_info
        return {
            "success": True,
            "message": "设备已连接",
            "device": {
                "id": request.device_id,
                "screen": {"width": screen.width, "height": screen.height}
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/disconnect")
async def disconnect_device():
    """断开设备."""
    global device_controller

    if device_controller:
        await device_controller.disconnect()
        device_controller = None
        return {"success": True, "message": "已断开连接"}
    return {"success": False, "error": "未连接设备"}


@app.get("/api/screenshot")
async def get_screenshot():
    """获取屏幕截图."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        result = await device_controller.take_screenshot()
        if result.success:
            screenshot_data = result.data.get("screenshot")
            if screenshot_data:
                b64_image = base64.b64encode(screenshot_data).decode("utf-8")
                return {
                    "success": True,
                    "image": f"data:image/png;base64,{b64_image}"
                }
        return {"success": False, "error": "截图失败"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/tap")
async def tap(request: TapRequest):
    """点击屏幕."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        result = await device_controller.tap(Point(request.x, request.y))
        return {"success": result.success, "point": {"x": request.x, "y": request.y}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/swipe")
async def swipe(request: SwipeRequest):
    """滑动屏幕."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        screen = device_controller.device.screen_info
        cx, cy = screen.width // 2, screen.height // 2

        if request.direction == "up":
            start, end = Point(cx, int(screen.height * 0.7)), Point(cx, int(screen.height * 0.3))
        elif request.direction == "down":
            start, end = Point(cx, int(screen.height * 0.3)), Point(cx, int(screen.height * 0.7))
        elif request.direction == "left":
            start, end = Point(int(screen.width * 0.8), cy), Point(int(screen.width * 0.2), cy)
        else:  # right
            start, end = Point(int(screen.width * 0.2), cy), Point(int(screen.width * 0.8), cy)

        result = await device_controller.swipe(start, end)
        return {"success": result.success, "direction": request.direction}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/input")
async def input_text(request: InputRequest):
    """输入文本."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        result = await device_controller.input_text(request.text)
        return {"success": result.success, "text": request.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/key/{key}")
async def press_key(key: str):
    """按键."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        result = await device_controller.press_key(key.upper())
        return {"success": result.success, "key": key}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/elements")
async def get_elements():
    """获取UI元素."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        elements = await device_controller.get_ui_hierarchy()
        print(f"[Elements] 原始元素数量: {len(elements)}")
        
        # 返回有标识信息的元素，或输入框
        result = []
        for e in elements:
            text = e.get("text") or ""
            desc = e.get("content_desc") or ""
            class_name = (e.get("class_name") or "").lower()
            is_input = "edittext" in class_name or "input" in class_name
            display_text = text or desc or f"[{e.get('class_name', 'unknown')}]"
            
            # 有标识信息的元素，或者是输入框
            if ((text or desc) or is_input) and e.get("center"):
                result.append({
                    "text": display_text,
                    "raw_text": text,
                    "content_desc": desc,
                    "center": e.get("center"),
                    "bounds": e.get("bounds"),
                    "clickable": e.get("clickable", False),
                    "class": e.get("class_name", "")
                })
        
        print(f"[Elements] 过滤后元素数量: {len(result)}")
        # 打印前10个元素用于调试
        for i, elem in enumerate(result[:10]):
            print(f"  [{i}] {elem['text'][:30] if elem['text'] else 'N/A'}")
        
        return {"success": True, "elements": result[:50], "total": len(elements)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/elements/debug")
async def get_elements_debug():
    """获取UI元素调试信息，保存原始XML."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        # 保存XML到文件
        elements = await device_controller.get_ui_hierarchy(save_xml=True)
        return {
            "success": True, 
            "total_elements": len(elements),
            "message": "XML已保存到 ui_hierarchy.xml，请查看项目根目录"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/click_text")
async def click_text(request: InputRequest):
    """点击包含指定文本的元素."""
    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        elements = await device_controller.get_ui_hierarchy()
        for elem in elements:
            elem_text = elem.get("text") or elem.get("content_desc") or ""
            if request.text in elem_text and elem.get("center"):
                center = elem["center"]
                result = await device_controller.tap(Point(center[0], center[1]))
                return {"success": result.success, "clicked": elem_text, "point": center}
        return {"success": False, "error": f"未找到: {request.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


class AITaskRequest(BaseModel):
    instruction: str


# 任务计划存储
current_task_plan: dict | None = None


@app.post("/api/ai/plan_task")
async def ai_plan_task_new(request: AITaskRequest):
    """AI生成总任务计划（不执行）."""
    global current_task_plan, device_controller

    try:
        # 每次任务都重新初始化LLM - 使用SSH隧道本地模型（避免记忆残留）
        llm_config = LLMConfig(
            provider=LLMProviderType.OPENAI,
            model="Qwen3-VL-8B-Instruct",
            api_key="not-needed",
            base_url="http://localhost:8000/v1",
            temperature=0.7,
            max_tokens=4096,
            timeout=120
        )
        local_llm_provider = OpenAIProvider(llm_config)
        await local_llm_provider.initialize()
        print("[AI] 重新初始化LLM实例，确保无记忆残留")

        from mobile_use.domain.services.agents.dynamic_planner import DynamicTaskPlanner, UIContext

        planner = DynamicTaskPlanner(llm_provider=local_llm_provider)
        
        # 获取当前UI上下文（如果已连接设备）
        ui_context = None
        if device_controller:
            elements = await device_controller.get_ui_hierarchy()
            screenshot_result = await device_controller.take_screenshot()
            # 提取截图数据（ActionResult.data 是 dict，包含 screenshot 字段）
            screenshot_bytes = None
            if screenshot_result and screenshot_result.success:
                data = screenshot_result.data
                if isinstance(data, dict) and "screenshot" in data:
                    screenshot_bytes = data["screenshot"]
                elif isinstance(data, bytes):
                    screenshot_bytes = data
            ui_context = UIContext(
                elements=elements,
                screenshot=screenshot_bytes
            )

        # 生成任务计划
        task_plan = await planner.generate_task_plan(request.instruction, ui_context)
        
        # 存储任务计划
        current_task_plan = {
            "original_task": task_plan.original_task,
            "task_summary": task_plan.task_summary,
            "steps": task_plan.steps,
            "potential_issues": task_plan.potential_issues,
            "success_criteria": task_plan.success_criteria,
            "estimated_steps": task_plan.estimated_steps,
            "confidence": task_plan.confidence
        }

        return {
            "success": True,
            "plan": current_task_plan
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/ai/current_plan")
async def get_current_plan():
    """获取当前任务计划."""
    global current_task_plan
    if current_task_plan:
        return {"success": True, "plan": current_task_plan}
    return {"success": False, "error": "没有当前任务计划"}


@app.post("/api/ai/execute")
async def ai_execute_task(request: AITaskRequest):
    """AI执行自然语言任务 - 使用模块化动态规划."""
    global orchestrator

    if not device_controller:
        return {"success": False, "error": "未连接设备"}

    try:
        # 每次执行都重新初始化LLM - 使用SSH隧道本地Qwen3-VL-8B模型（避免记忆残留）
        llm_config = LLMConfig(
            provider=LLMProviderType.OPENAI,
            model="Qwen3-VL-8B-Instruct",
            api_key="not-needed",
            base_url="http://localhost:8000/v1",
            temperature=0.7,
            max_tokens=4096,
            timeout=600,
            retry_attempts=5
        )
        local_llm_provider = OpenAIProvider(llm_config)
        await local_llm_provider.initialize()
        print("[AI] 重新初始化LLM实例，确保无记忆残留")

        # 使用模块化编排器
        from mobile_use.domain.services.agents.dynamic_planner import DynamicTaskPlanner, TaskPlan
        from mobile_use.domain.services.agents.modular_orchestrator import ModularOrchestrator

        # 创建动态规划器
        planner = DynamicTaskPlanner(llm_provider=local_llm_provider)
        
        # 如果有当前任务计划，设置到 planner 中
        if current_task_plan:
            planner.current_task_plan = TaskPlan(
                original_task=current_task_plan.get("original_task", request.instruction),
                task_summary=current_task_plan.get("task_summary", request.instruction),
                steps=current_task_plan.get("steps", []),
                potential_issues=current_task_plan.get("potential_issues", []),
                success_criteria=current_task_plan.get("success_criteria", "任务完成"),
                estimated_steps=current_task_plan.get("estimated_steps", 10),
                confidence=current_task_plan.get("confidence", 0.8)
            )
            print(f"[Execute] 使用总任务计划: {planner.current_task_plan.task_summary}")
        
        # 创建动作执行器
        action_executor = ActionExecutorAgent(
            device_controller=device_controller,
            llm_provider=local_llm_provider
        )
        
        # 创建模块化编排器
        modular_orchestrator = ModularOrchestrator(
            planner=planner,
            action_executor=action_executor,
            device_controller=device_controller,
            max_steps=100,
            step_timeout_ms=30000
        )

        # 重置进度
        task_progress["running"] = True
        task_progress["status"] = "planning"
        task_progress["current_step"] = 0
        task_progress["total_steps"] = 0
        task_progress["current_action"] = "正在规划任务..."
        task_progress["steps"] = []
        task_progress["completed_steps"] = []

        # 设置进度回调
        def on_progress(step_index: int, total: int, action: str, description: str, target: str = ""):
            # 记录已完成的步骤
            if step_index > 0 and len(task_progress["completed_steps"]) < step_index:
                task_progress["completed_steps"].append({
                    "action": action,
                    "description": description,
                    "target": target
                })
            
            task_progress["current_step"] = step_index + 1
            task_progress["total_steps"] = total
            task_progress["current_action"] = description
            task_progress["status"] = "executing"
        
        modular_orchestrator.on_progress = on_progress
        
        # 设置停止检查回调
        def check_stop():
            return task_progress.get("stop_requested", False)
        modular_orchestrator.stop_check = check_stop

        # 执行AI任务（使用模块化编排器）
        task_progress["status"] = "executing"
        task_progress["stop_requested"] = False  # 重置停止标志
        result = await modular_orchestrator.execute_task(request.instruction)

        # 更新已完成步骤列表
        task_progress["completed_steps"] = [
            {
                "action": step.action,
                "description": step.description,
                "target": step.target
            }
            for step in result.completed_steps
        ]

        # 更新最终进度
        task_progress["running"] = False
        task_progress["status"] = "completed" if result.success else "failed"
        task_progress["current_step"] = result.steps_executed
        task_progress["total_steps"] = result.steps_executed
        task_progress["current_action"] = "任务完成" if result.success else f"任务失败: {result.error}"

        return {
            "success": result.success,
            "instruction": request.instruction,
            "steps_executed": result.steps_executed,
            "total_steps": result.steps_executed,
            "duration_ms": result.duration_ms,
            "completed_steps": [
                {"action": s.action, "description": s.description, "target": s.target}
                for s in result.completed_steps
            ],
            "error": result.error
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        task_progress["status"] = "failed"
        task_progress["running"] = False
        task_progress["current_action"] = f"错误: {str(e)}"
        return {"success": False, "error": str(e)}


@app.get("/api/ai/progress")
async def get_task_progress():
    """获取当前任务进度."""
    return task_progress


@app.post("/api/ai/stop")
async def stop_task():
    """停止当前正在执行的任务."""
    if task_progress["running"]:
        task_progress["stop_requested"] = True
        task_progress["current_action"] = "正在停止..."
        return {"success": True, "message": "已发送停止请求"}
    return {"success": False, "message": "没有正在执行的任务"}


@app.post("/api/ai/plan")
async def ai_plan_task(request: AITaskRequest):
    """AI规划任务（只规划不执行）."""
    try:
        # 每次规划都重新初始化LLM - 使用SSH隧道本地模型（避免记忆残留）
        llm_config = LLMConfig(
            provider=LLMProviderType.OPENAI,
            model="Qwen3-VL-8B-Instruct",
            api_key="not-needed",
            base_url="http://localhost:8000/v1",
            temperature=0.7,
            max_tokens=4096,
            timeout=120
        )
        local_llm_provider = OpenAIProvider(llm_config)
        await local_llm_provider.initialize()
        print("[AI] 重新初始化LLM实例，确保无记忆残留")

        # 获取UI元素（如果已连接）
        ui_elements = []
        if device_controller:
            ui_elements = await device_controller.get_ui_hierarchy()

        # 创建任务规划代理
        task_planner = TaskPlannerAgent(llm_provider=local_llm_provider)

        from mobile_use.domain.services.agents.base import AgentContext
        context = AgentContext(
            task_id="plan-only",
            instruction=request.instruction,
            ui_elements=ui_elements
        )

        # 执行规划
        result = await task_planner.run(context)

        if result.success:
            plan = result.data.get("plan", {})
            return {
                "success": True,
                "instruction": request.instruction,
                "plan": plan,
                "confidence": result.confidence
            }
        else:
            return {"success": False, "error": result.error}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def get_html_page() -> str:
    """返回Web控制台HTML页面."""
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mobile-Use Web Console</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            text-align: center;
            padding: 20px 0;
            border-bottom: 1px solid #333;
            margin-bottom: 20px;
        }
        header h1 {
            font-size: 28px;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .main-content {
            display: grid;
            grid-template-columns: 400px 1fr;
            gap: 20px;
        }
        .phone-container {
            background: #0f0f23;
            border-radius: 20px;
            padding: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }
        .phone-screen {
            position: relative;
            background: #000;
            border-radius: 10px;
            overflow: hidden;
            cursor: crosshair;
        }
        .phone-screen img {
            width: 100%;
            display: block;
        }
        .phone-screen .placeholder {
            width: 100%;
            height: 600px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #666;
            font-size: 18px;
        }
        .control-panel {
            background: #0f0f23;
            border-radius: 15px;
            padding: 20px;
        }
        .section {
            margin-bottom: 25px;
        }
        .section h3 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 16px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .btn-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-primary {
            background: linear-gradient(135deg, #00d4ff, #0099cc);
            color: #fff;
        }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0,212,255,0.4); }
        .btn-success {
            background: linear-gradient(135deg, #00c853, #009624);
            color: #fff;
        }
        .btn-success:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0,200,83,0.4); }
        .btn-danger {
            background: linear-gradient(135deg, #ff5252, #d32f2f);
            color: #fff;
        }
        .btn-warning {
            background: linear-gradient(135deg, #ffc107, #ff9800);
            color: #000;
        }
        .btn-secondary {
            background: #333;
            color: #fff;
        }
        .btn-secondary:hover { background: #444; }
        .direction-pad {
            display: grid;
            grid-template-columns: repeat(3, 60px);
            grid-template-rows: repeat(3, 60px);
            gap: 5px;
            justify-content: center;
        }
        .direction-pad .btn {
            padding: 0;
            font-size: 20px;
        }
        .direction-pad .center { grid-column: 2; grid-row: 2; }
        .direction-pad .up { grid-column: 2; grid-row: 1; }
        .direction-pad .down { grid-column: 2; grid-row: 3; }
        .direction-pad .left { grid-column: 1; grid-row: 2; }
        .direction-pad .right { grid-column: 3; grid-row: 2; }
        .input-group {
            display: flex;
            gap: 10px;
        }
        .input-group input {
            flex: 1;
            padding: 12px 15px;
            border: 2px solid #333;
            border-radius: 8px;
            background: #1a1a2e;
            color: #fff;
            font-size: 14px;
        }
        .input-group input:focus {
            outline: none;
            border-color: #00d4ff;
        }
        .status {
            padding: 10px 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 14px;
        }
        .status.connected { background: rgba(0,200,83,0.2); border: 1px solid #00c853; }
        .status.disconnected { background: rgba(255,82,82,0.2); border: 1px solid #ff5252; }
        .log {
            background: #0a0a15;
            border-radius: 8px;
            padding: 15px;
            height: 200px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 12px;
        }
        .log-entry { padding: 3px 0; border-bottom: 1px solid #222; }
        .log-entry.success { color: #00c853; }
        .log-entry.error { color: #ff5252; }
        .log-entry.info { color: #00d4ff; }
        .elements-list {
            max-height: 300px;
            overflow-y: auto;
            background: #0a0a15;
            border-radius: 8px;
            padding: 10px;
        }
        .element-item {
            padding: 8px 12px;
            margin: 5px 0;
            background: #1a1a2e;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 13px;
        }
        .element-item:hover { background: #2a2a4e; transform: translateX(5px); }
        
        /* 任务进度条样式 */
        .task-progress {
            background: #0a0a15;
            border-radius: 12px;
            padding: 15px;
            margin-top: 15px;
        }
        .progress-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 14px;
        }
        .progress-bar-container {
            background: #1a1a2e;
            border-radius: 10px;
            height: 20px;
            overflow: hidden;
            margin-bottom: 15px;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #7b2cbf, #bf7bff);
            border-radius: 10px;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
        }
        .subtask-list {
            max-height: 200px;
            overflow-y: auto;
        }
        .subtask-item {
            display: flex;
            align-items: center;
            padding: 8px 12px;
            margin: 5px 0;
            background: #1a1a2e;
            border-radius: 8px;
            font-size: 13px;
            transition: all 0.3s;
        }
        .subtask-item.pending { opacity: 0.5; }
        .subtask-item.running { 
            background: linear-gradient(90deg, #2a1a4e, #1a1a2e);
            border-left: 3px solid #bf7bff;
        }
        .subtask-item.completed { 
            background: rgba(0, 200, 83, 0.1);
            border-left: 3px solid #00c853;
        }
        .subtask-item.failed { 
            background: rgba(255, 82, 82, 0.1);
            border-left: 3px solid #ff5252;
        }
        .subtask-icon {
            width: 20px;
            height: 20px;
            margin-right: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .subtask-icon.pending::before { content: '○'; color: #666; }
        .subtask-icon.running::before { content: '◉'; color: #bf7bff; animation: pulse 1s infinite; }
        .subtask-icon.completed::before { content: '✓'; color: #00c853; }
        .subtask-icon.failed::before { content: '✗'; color: #ff5252; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .subtask-name { flex: 1; }
        .subtask-status { font-size: 11px; color: #888; }
        
        .click-indicator {
            position: absolute;
            width: 30px;
            height: 30px;
            border: 3px solid #00d4ff;
            border-radius: 50%;
            pointer-events: none;
            animation: click-ripple 0.5s ease-out forwards;
        }
        @keyframes click-ripple {
            0% { transform: translate(-50%, -50%) scale(0); opacity: 1; }
            100% { transform: translate(-50%, -50%) scale(2); opacity: 0; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Mobile-Use Web Console</h1>
            <p style="color: #888; margin-top: 10px;">AI驱动的移动设备自动化控制台</p>
        </header>

        <div class="main-content">
            <div class="phone-container">
                <div id="status" class="status disconnected">未连接设备</div>
                <div class="phone-screen" id="phoneScreen" onclick="handleScreenClick(event)">
                    <div class="placeholder" id="placeholder">点击"连接设备"开始</div>
                    <img id="screenshot" style="display:none;" />
                </div>
                <div style="margin-top: 15px; text-align: center;">
                    <button class="btn btn-primary" onclick="refreshScreen()">刷新屏幕</button>
                    <button class="btn btn-secondary" onclick="toggleAutoRefresh()">自动刷新: <span id="autoRefreshStatus">关</span></button>
                </div>
            </div>

            <div class="control-panel">
                <div class="section">
                    <h3>设备连接</h3>
                    <div class="input-group">
                        <input type="text" id="deviceId" value="emulator-5554" placeholder="设备ID">
                        <button class="btn btn-success" onclick="connectDevice()">连接</button>
                        <button class="btn btn-danger" onclick="disconnectDevice()">断开</button>
                    </div>
                </div>

                <div class="section">
                    <h3>方向控制</h3>
                    <div class="direction-pad">
                        <div></div>
                        <button class="btn btn-secondary up" onclick="swipe('up')">↑</button>
                        <div></div>
                        <button class="btn btn-secondary left" onclick="swipe('left')">←</button>
                        <button class="btn btn-primary center" onclick="pressKey('HOME')">●</button>
                        <button class="btn btn-secondary right" onclick="swipe('right')">→</button>
                        <div></div>
                        <button class="btn btn-secondary down" onclick="swipe('down')">↓</button>
                        <div></div>
                    </div>
                </div>

                <div class="section">
                    <h3>快捷按键</h3>
                    <div class="btn-group">
                        <button class="btn btn-secondary" onclick="pressKey('BACK')">返回</button>
                        <button class="btn btn-secondary" onclick="pressKey('HOME')">主页</button>
                        <button class="btn btn-secondary" onclick="pressKey('RECENT')">最近</button>
                        <button class="btn btn-secondary" onclick="pressKey('MENU')">菜单</button>
                    </div>
                </div>

                <div class="section">
                    <h3>文本输入</h3>
                    <div class="input-group">
                        <input type="text" id="inputText" placeholder="输入文本...">
                        <button class="btn btn-primary" onclick="sendText()">发送</button>
                    </div>
                </div>

                <div class="section">
                    <h3>点击文本元素</h3>
                    <div class="input-group">
                        <input type="text" id="clickText" placeholder="要点击的文本...">
                        <button class="btn btn-warning" onclick="clickByText()">点击</button>
                        <button class="btn btn-secondary" onclick="loadElements()">刷新元素</button>
                    </div>
                    <div class="elements-list" id="elementsList" style="margin-top: 10px;"></div>
                </div>

                <div class="section" style="background: linear-gradient(135deg, #1a0a2e 0%, #2a1a4e 100%); padding: 20px; border-radius: 12px; border: 2px solid #7b2cbf;">
                    <h3 style="color: #bf7bff;">AI 智能控制</h3>
                    <p style="color: #888; font-size: 12px; margin-bottom: 15px;">输入自然语言指令，AI将先规划总任务再执行子任务</p>
                    <div class="input-group">
                        <input type="text" id="aiInstruction" placeholder="例如：打开QQ给张三发消息说你好..." style="border-color: #7b2cbf;">
                        <button class="btn" id="btnExecuteAI" style="background: linear-gradient(135deg, #7b2cbf, #bf7bff); color: #fff;" onclick="executeAI()">执行</button>
                        <button class="btn" id="btnStopAI" style="background: #ff5252; color: #fff; opacity: 0.5;" onclick="stopAI()" disabled>停止</button>
                    </div>
                    <div style="margin-top: 10px;">
                        <button class="btn btn-secondary" style="font-size: 12px; padding: 8px 12px;" onclick="setAICommand('返回桌面')">返回桌面</button>
                        <button class="btn btn-secondary" style="font-size: 12px; padding: 8px 12px;" onclick="setAICommand('打开设置')">打开设置</button>
                        <button class="btn btn-secondary" style="font-size: 12px; padding: 8px 12px;" onclick="setAICommand('打开QQ给张三发消息')">发QQ消息</button>
                    </div>
                    
                    <!-- 任务计划显示区域 -->
                    <div id="taskPlanArea" style="margin-top: 15px; display: none;">
                        <div style="background: #0a0a15; border-radius: 8px; padding: 15px; border: 1px solid #2196f3;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <h4 style="color: #2196f3; margin: 0;">📋 任务计划</h4>
                                <span id="planConfidence" style="color: #888; font-size: 12px;"></span>
                            </div>
                            <div id="taskSummary" style="color: #fff; font-size: 14px; margin-bottom: 10px; padding: 8px; background: #1a1a2e; border-radius: 5px;"></div>
                            <div style="margin-bottom: 10px;">
                                <div style="color: #888; font-size: 12px; margin-bottom: 5px;">预期步骤：</div>
                                <div id="planSteps" style="font-size: 13px;"></div>
                            </div>
                            <div id="planIssues" style="display: none; margin-bottom: 10px;">
                                <div style="color: #ff9800; font-size: 12px; margin-bottom: 5px;">⚠️ 可能的问题：</div>
                                <div id="planIssuesList" style="font-size: 12px; color: #888;"></div>
                            </div>
                            <div style="color: #888; font-size: 12px;">
                                <span>✓ 成功标准：</span>
                                <span id="successCriteria" style="color: #00c853;"></span>
                            </div>
                            <div style="color: #888; font-size: 12px; margin-top: 5px;">
                                <span>预估操作数：</span>
                                <span id="estimatedSteps" style="color: #2196f3;"></span>
                            </div>
                        </div>
                    </div>
                    
                    <div id="aiResult" style="margin-top: 15px; display: none;">
                        <!-- 进度条区域 -->
                        <div class="task-progress" id="taskProgress">
                            <div class="progress-header">
                                <span id="taskTitle">执行任务中...</span>
                                <span id="taskPercent">0%</span>
                            </div>
                            <div class="progress-bar-container">
                                <div class="progress-bar" id="progressBar" style="width: 0%"></div>
                            </div>
                            <div class="subtask-list" id="subtaskList"></div>
                        </div>
                        <!-- 结果区域 -->
                        <div id="aiResultContent" style="margin-top: 10px; padding: 10px; background: #0a0a15; border-radius: 8px;"></div>
                    </div>
                </div>

                <div class="section">
                    <h3>操作日志</h3>
                    <div class="log" id="log"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let isConnected = false;
        let autoRefresh = false;
        let autoRefreshInterval = null;
        let screenWidth = 1080;
        let screenHeight = 1920;

        function log(message, type = 'info') {
            const logDiv = document.getElementById('log');
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + type;
            entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            logDiv.insertBefore(entry, logDiv.firstChild);
        }

        async function api(endpoint, method = 'GET', data = null) {
            const options = { method, headers: { 'Content-Type': 'application/json' } };
            if (data) options.body = JSON.stringify(data);
            const response = await fetch('/api' + endpoint, options);
            return await response.json();
        }

        async function connectDevice() {
            const deviceId = document.getElementById('deviceId').value;
            log('正在连接: ' + deviceId);
            const result = await api('/connect', 'POST', { device_id: deviceId });
            if (result.success) {
                isConnected = true;
                screenWidth = result.device.screen.width;
                screenHeight = result.device.screen.height;
                document.getElementById('status').className = 'status connected';
                document.getElementById('status').textContent = `已连接: ${deviceId} (${screenWidth}x${screenHeight})`;
                log('连接成功!', 'success');
                refreshScreen();
                loadElements();
            } else {
                log('连接失败: ' + result.error, 'error');
            }
        }

        async function disconnectDevice() {
            const result = await api('/disconnect', 'POST');
            isConnected = false;
            document.getElementById('status').className = 'status disconnected';
            document.getElementById('status').textContent = '未连接设备';
            document.getElementById('screenshot').style.display = 'none';
            document.getElementById('placeholder').style.display = 'flex';
            log('已断开连接');
        }

        async function refreshScreen() {
            if (!isConnected) return;
            const result = await api('/screenshot');
            if (result.success) {
                document.getElementById('screenshot').src = result.image;
                document.getElementById('screenshot').style.display = 'block';
                document.getElementById('placeholder').style.display = 'none';
            }
        }

        function toggleAutoRefresh() {
            autoRefresh = !autoRefresh;
            document.getElementById('autoRefreshStatus').textContent = autoRefresh ? '开' : '关';
            if (autoRefresh) {
                autoRefreshInterval = setInterval(refreshScreen, 1000);
            } else {
                clearInterval(autoRefreshInterval);
            }
        }

        async function handleScreenClick(event) {
            if (!isConnected) return;
            const img = document.getElementById('screenshot');
            if (img.style.display === 'none') return;

            const rect = img.getBoundingClientRect();
            const scaleX = screenWidth / rect.width;
            const scaleY = screenHeight / rect.height;
            const x = Math.round((event.clientX - rect.left) * scaleX);
            const y = Math.round((event.clientY - rect.top) * scaleY);

            // 显示点击效果
            const indicator = document.createElement('div');
            indicator.className = 'click-indicator';
            indicator.style.left = event.clientX - rect.left + 'px';
            indicator.style.top = event.clientY - rect.top + 'px';
            document.getElementById('phoneScreen').appendChild(indicator);
            setTimeout(() => indicator.remove(), 500);

            log(`点击: (${x}, ${y})`);
            const result = await api('/tap', 'POST', { x, y });
            if (result.success) {
                log('点击成功', 'success');
                setTimeout(refreshScreen, 300);
            } else {
                log('点击失败: ' + result.error, 'error');
            }
        }

        async function swipe(direction) {
            if (!isConnected) return;
            log('滑动: ' + direction);
            const result = await api('/swipe', 'POST', { direction });
            if (result.success) {
                log('滑动成功', 'success');
                setTimeout(refreshScreen, 500);
            } else {
                log('滑动失败: ' + result.error, 'error');
            }
        }

        async function pressKey(key) {
            if (!isConnected) return;
            log('按键: ' + key);
            const result = await api('/key/' + key, 'POST');
            if (result.success) {
                log('按键成功', 'success');
                setTimeout(refreshScreen, 300);
            } else {
                log('按键失败: ' + result.error, 'error');
            }
        }

        async function sendText() {
            if (!isConnected) return;
            const text = document.getElementById('inputText').value;
            if (!text) return;
            log('输入: ' + text);
            const result = await api('/input', 'POST', { text });
            if (result.success) {
                log('输入成功', 'success');
                document.getElementById('inputText').value = '';
                setTimeout(refreshScreen, 300);
            } else {
                log('输入失败: ' + result.error, 'error');
            }
        }

        async function clickByText() {
            if (!isConnected) return;
            const text = document.getElementById('clickText').value;
            if (!text) return;
            log('点击文本: ' + text);
            const result = await api('/click_text', 'POST', { text });
            if (result.success) {
                log(`点击成功: ${result.clicked}`, 'success');
                setTimeout(refreshScreen, 300);
            } else {
                log('点击失败: ' + result.error, 'error');
            }
        }

        async function loadElements() {
            if (!isConnected) return;
            const result = await api('/elements');
            const list = document.getElementById('elementsList');
            list.innerHTML = '';
            if (result.success && result.elements) {
                result.elements.forEach(elem => {
                    if (elem.text) {
                        const div = document.createElement('div');
                        div.className = 'element-item';
                        div.textContent = elem.text;
                        div.onclick = () => {
                            document.getElementById('clickText').value = elem.text;
                            clickByText();
                        };
                        list.appendChild(div);
                    }
                });
                log(`加载了 ${result.elements.length} 个元素`, 'info');
            }
        }

        // AI控制函数
        function setAICommand(cmd) {
            document.getElementById('aiInstruction').value = cmd;
        }

        // 当前任务计划
        let currentPlan = null;
        
        // 已完成的步骤历史记录
        let completedSteps = [];
        
        // 显示任务计划
        function displayTaskPlan(plan) {
            currentPlan = plan;
            document.getElementById('taskPlanArea').style.display = 'block';
            document.getElementById('taskSummary').textContent = plan.task_summary;
            document.getElementById('planConfidence').textContent = `置信度: ${Math.round(plan.confidence * 100)}%`;
            document.getElementById('successCriteria').textContent = plan.success_criteria;
            document.getElementById('estimatedSteps').textContent = plan.estimated_steps + ' 步';
            
            // 显示步骤
            const stepsDiv = document.getElementById('planSteps');
            stepsDiv.innerHTML = '';
            plan.steps.forEach((step, i) => {
                const div = document.createElement('div');
                div.style.cssText = 'padding: 5px 10px; margin: 3px 0; background: #1a1a2e; border-radius: 5px; border-left: 3px solid #2196f3;';
                div.innerHTML = `<span style="color: #2196f3; margin-right: 8px;">${i + 1}.</span><span style="color: #ddd;">${step}</span>`;
                stepsDiv.appendChild(div);
            });
            
            // 显示可能的问题
            if (plan.potential_issues && plan.potential_issues.length > 0) {
                document.getElementById('planIssues').style.display = 'block';
                const issuesDiv = document.getElementById('planIssuesList');
                issuesDiv.innerHTML = plan.potential_issues.map(issue => 
                    `<div style="padding: 3px 0;">• ${issue}</div>`
                ).join('');
            } else {
                document.getElementById('planIssues').style.display = 'none';
            }
            
        }
        
        // 更新进度条
        function updateProgress(current, total, currentAction) {
            const percent = total > 0 ? Math.round((current / total) * 100) : 0;
            document.getElementById('progressBar').style.width = percent + '%';
            document.getElementById('taskPercent').textContent = percent + '%';
        }
        
        // 渲染步骤列表
        function renderStepsList(currentAction) {
            const subtaskList = document.getElementById('subtaskList');
            subtaskList.innerHTML = '';
            
            // 显示已完成的步骤
            completedSteps.forEach((step, i) => {
                const div = document.createElement('div');
                div.className = 'subtask-item completed';
                div.innerHTML = `<div class="subtask-icon completed">✓</div>
                    <div class="subtask-name">${step.description || step.action}</div>
                    <div class="subtask-status">${step.target || ''}</div>`;
                subtaskList.appendChild(div);
            });
            
            // 显示当前正在执行的步骤
            if (currentAction) {
                const div = document.createElement('div');
                div.className = 'subtask-item running';
                div.innerHTML = `<div class="subtask-icon running"></div>
                    <div class="subtask-name">${currentAction}</div>
                    <div class="subtask-status">执行中...</div>`;
                subtaskList.appendChild(div);
            }
        }

        let progressInterval = null;
        
        async function pollProgress() {
            try {
                const progress = await api('/ai/progress', 'GET');
                if (progress.running) {
                    // 更新已完成的步骤
                    if (progress.completed_steps && progress.completed_steps.length > completedSteps.length) {
                        completedSteps = progress.completed_steps;
                    }
                    updateProgress(progress.current_step, progress.total_steps);
                    renderStepsList(progress.current_action);
                    document.getElementById('aiResultContent').innerHTML = 
                        `<div style="color: #2196f3;">正在执行: ${progress.current_action}</div>`;
                }
                return progress;
            } catch (e) {
                console.error('获取进度失败:', e);
                return null;
            }
        }

        async function stopAI() {
            try {
                const result = await api('/ai/stop', 'POST');
                if (result.success) {
                    log('已发送停止请求', 'info');
                } else {
                    log(result.message || '停止失败', 'error');
                }
            } catch (e) {
                log('停止请求失败: ' + e.message, 'error');
            }
        }

        function showStopButton(show) {
            const btnExecute = document.getElementById('btnExecuteAI');
            const btnStop = document.getElementById('btnStopAI');
            if (show) {
                btnExecute.disabled = true;
                btnExecute.style.opacity = '0.5';
                btnStop.disabled = false;
                btnStop.style.opacity = '1';
            } else {
                btnExecute.disabled = false;
                btnExecute.style.opacity = '1';
                btnStop.disabled = true;
                btnStop.style.opacity = '0.5';
            }
        }

        async function executeAI() {
            const originalInput = document.getElementById('aiInstruction').value;
            
            if (!originalInput) {
                log('请输入AI指令', 'error');
                return;
            }
            
            // 禁用执行按钮，显示停止按钮
            document.getElementById('btnExecuteAI').disabled = true;
            document.getElementById('btnExecuteAI').textContent = '规划中...';
            showStopButton(true);
            
            const resultDiv = document.getElementById('aiResult');
            const contentDiv = document.getElementById('aiResultContent');
            resultDiv.style.display = 'block';
            contentDiv.innerHTML = '<div style="color: #64b5f6;">正在规划总任务...</div>';
            
            // 第一步：规划总任务
            log('正在规划总任务...', 'info');
            try {
                const planResult = await api('/ai/plan_task', 'POST', { instruction: originalInput });
                if (planResult.success) {
                    displayTaskPlan(planResult.plan);
                    log('总任务规划完成', 'success');
                } else {
                    log('规划失败: ' + planResult.error, 'warning');
                    // 规划失败也继续执行，使用原始任务
                }
            } catch (e) {
                log('规划请求失败: ' + e.message, 'warning');
            }
            
            // 第二步：执行子任务
            document.getElementById('btnExecuteAI').textContent = '执行中...';
            const taskToExecute = currentPlan ? currentPlan.task_summary : originalInput;

            // 重置已完成步骤
            completedSteps = [];
            
            // 显示任务标题
            document.getElementById('taskTitle').textContent = taskToExecute;
            
            // 使用预估步数
            const estimatedSteps = currentPlan ? currentPlan.estimated_steps : 10;
            updateProgress(0, estimatedSteps);
            renderStepsList('AI正在执行子任务...');
            log('开始执行: ' + taskToExecute, 'info');

            try {
                // 启动进度轮询
                progressInterval = setInterval(() => pollProgress(), 500);
                
                // 执行任务（使用处理后的任务）
                const result = await api('/ai/execute', 'POST', { instruction: taskToExecute });
                
                // 停止轮询
                if (progressInterval) {
                    clearInterval(progressInterval);
                    progressInterval = null;
                }

                if (result.success) {
                    // 最后获取一次进度，确保显示所有已完成步骤
                    const finalProgress = await api('/ai/progress', 'GET');
                    if (finalProgress.completed_steps) {
                        completedSteps = finalProgress.completed_steps;
                    }
                    updateProgress(result.steps_executed, result.steps_executed);
                    renderStepsList(null);  // 不显示当前执行步骤
                    
                    let html = '<div style="color: #00c853; font-weight: bold; font-size: 16px;">✓ 任务完成!</div>';
                    html += `<div style="margin-top: 8px; color: #888;">耗时: ${result.duration_ms}ms，共 ${result.steps_executed} 步</div>`;
                    contentDiv.innerHTML = html;
                    log('AI任务完成: ' + result.steps_executed + '步', 'success');
                    setTimeout(refreshScreen, 500);
                } else {
                    // 获取已完成的步骤
                    const finalProgress = await api('/ai/progress', 'GET');
                    if (finalProgress.completed_steps) {
                        completedSteps = finalProgress.completed_steps;
                    }
                    renderStepsList(null);
                    contentDiv.innerHTML = `<div style="color: #ff5252;">✗ 执行失败: ${result.error}</div>`;
                    log('AI任务失败: ' + result.error, 'error');
                }
                
                // 恢复按钮状态
                showStopButton(false);
                resetPlanButton();
            } catch (e) {
                // 停止轮询
                if (progressInterval) {
                    clearInterval(progressInterval);
                    progressInterval = null;
                }
                contentDiv.innerHTML = `<div style="color: #ff5252;">✗ 错误: ${e.message}</div>`;
                log('AI错误: ' + e.message, 'error');
                
                // 恢复按钮状态
                showStopButton(false);
                resetPlanButton();
            }
        }
        
        // 恢复执行按钮状态
        function resetPlanButton() {
            // 清除当前计划，下次需要重新规划
            currentPlan = null;
            // 恢复执行按钮
            document.getElementById('btnExecuteAI').disabled = false;
            document.getElementById('btnExecuteAI').textContent = '执行';
            document.getElementById('btnExecuteAI').style.opacity = '1';
        }

        // Enter键执行AI
        document.getElementById('aiInstruction')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') executeAI();
        });

        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            if (e.key === 'ArrowUp') swipe('up');
            if (e.key === 'ArrowDown') swipe('down');
            if (e.key === 'ArrowLeft') swipe('left');
            if (e.key === 'ArrowRight') swipe('right');
            if (e.key === 'Backspace') pressKey('BACK');
            if (e.key === 'Home') pressKey('HOME');
        });
    </script>
</body>
</html>'''


if __name__ == "__main__":
    import uvicorn
    import sys
    
    # 从环境变量或命令行参数获取端口
    port = int(os.getenv("WEB_PORT", "8080"))
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    
    print("=" * 50)
    print("Mobile-Use Web Console")
    print("=" * 50)
    print(f"\n启动Web服务器...")
    print(f"打开浏览器访问: http://localhost:{port}")
    print("\n按 Ctrl+C 停止服务器")
    print(f"提示: 可以使用其他端口启动: python -m mobile_use.presentation.api.main <端口号>")
    uvicorn.run(app, host="0.0.0.0", port=port, access_log=False)
