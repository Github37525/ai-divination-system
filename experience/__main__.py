"""使用 ``python -m experience`` 启动本地多端体验服务。"""

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "experience.api:app",
        host=os.environ.get("EXPERIENCE_HOST", "0.0.0.0"),
        port=int(os.environ.get("EXPERIENCE_PORT", "8770")),
        reload=False,
    )
