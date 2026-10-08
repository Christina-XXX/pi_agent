"""自定义工具示例。

把写好的 .py 文件放到项目根目录的 tools/ 文件夹里即可被自动加载。
两种注册方式任选其一：

方式一：使用 @REGISTRY.tool 装饰器
方式二：定义 TOOLS 列表（每个元素是 deepseek_agent.tools.Tool 实例）
"""
from deepseek_agent.tools import REGISTRY, Tool

# ------------------ 方式一：装饰器 ------------------ #
@REGISTRY.tool(
    name="current_time",
    description="获取当前日期和时间。",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def current_time():
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")


# ------------------ 方式二：TOOLS 列表 ------------------ #
def _add(a: int, b: int) -> str:
    return f"{a} + {b} = {a + b}"


TOOLS = [
    Tool(
        name="add",
        description="计算两个整数之和。",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "第一个整数"},
                "b": {"type": "integer", "description": "第二个整数"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        },
        func=_add,
    ),
]
