package com.yijing.instrument

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelsTest {
    @Test
    fun lineSemanticsMatchSharedContract() {
        assertFalse(line(6).isYang)
        assertTrue(line(7).isYang)
        assertFalse(line(8).isYang)
        assertTrue(line(9).isYang)
    }

    private fun line(value: Int) = CastLine(
        lineIndex = 1,
        positionName = "初爻",
        fronts = 0,
        reverses = 3,
        value = value,
        lineType = "测试",
        moving = value == 6 || value == 9,
        triggerMode = "tap",
        motionEnergy = null,
    )
}
