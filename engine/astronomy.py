"""
engine/astronomy.py
计算四柱干支、真太阳时调整、旬空及六神
"""
from datetime import datetime, timedelta
from typing import Dict, Any

# 使用包内相对导入，彻底避免云端部署路径问题
from .config import TIANGAN, DIZHI, LIUSHEN_MAP


class AstronomyService:
    @staticmethod
    def calculate_true_solar_time(dt: datetime, longitude: float) -> datetime:
        """根据经度差计算真太阳时 (以东八区120度为基准)"""
        time_offset_minutes = (longitude - 120.0) * 4
        return dt + timedelta(minutes=time_offset_minutes)

    @staticmethod
    def get_ganzhi_calendar(dt: datetime, longitude: float = 120.0) -> Dict[str, Any]:
        """
        推算干支历法与神煞（基础演示算法）
        """
        true_dt = AstronomyService.calculate_true_solar_time(dt, longitude)
        
        # 演示用干支接口
        day_gan = "甲"
        day_zhi = "子"
        month_zhi = "午"
        
        # 计算旬空 (基于日柱)
        gan_idx = TIANGAN.index(day_gan)
        zhi_idx = DIZHI.index(day_zhi)
        xunkong_zhi1 = DIZHI[(zhi_idx - gan_idx + 10) % 12]
        xunkong_zhi2 = DIZHI[(zhi_idx - gan_idx + 11) % 12]
        
        return {
            "true_solar_time": true_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "day_ganzhi": f"{day_gan}{day_zhi}",
            "month_branch": month_zhi,
            "xunkong": [xunkong_zhi1, xunkong_zhi2],
            "liushen": LIUSHEN_MAP.get(day_gan, [])
        }