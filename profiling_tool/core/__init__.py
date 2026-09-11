"""ProfilingTool コアSDK(Phase1): span / counter / event / GpuTimestampQuery。

対象(VLM/Sound/GI/VideoFactory)を一切知らない。対象固有の知識はadapters/に隔離する。

ProfilingTool_DESIGN.mdはこのSDKをC++シグネチャで示しているが、本実装は
adapters/以下(設計書でも既にPython指定)と言語を統一し、Python実装として進める
(実測対象のSoundMiddleware/DynamicGIMiddleware等がまだワークスペースに存在せず、
バイナリ互換を優先する理由が無いため)。
"""

__version__ = "0.1.0"
