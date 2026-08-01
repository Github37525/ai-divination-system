# 天文铜仪原生客户端

本目录是 H5 之外的两套真原生客户端：

- `ios/`：SwiftUI、Core Motion、Core Haptics、AVFoundation。
- `android/`：Jetpack Compose、Sensor Framework、VibrationEffect、SoundPool。
- `shared/`：跨端 API、状态与反馈契约；不共享 UI 代码。

两端都遵循同一条硬约束：传感器只决定触发时机和动作能量，爻值由服务端先锁定，客户端拿到锁定结果后才播放铜钱动画、声音和触觉。

默认生产 API 为 `https://ai-divination-experience.onrender.com`。开发环境可在 Xcode Scheme 或启动 Android 构建前设置环境变量 `EXPERIENCE_API_BASE_URL` 覆盖。

## 本地打开

### iOS

1. 安装 Xcode 26 和 XcodeGen。
2. 在 `native/ios` 执行 `xcodegen generate`。
3. 打开生成的 `DivinationInstrument.xcodeproj`，选择真机运行。

Core Motion、Core Haptics 和实际扬声器效果必须在 iPhone 真机验收。

### Android

1. 使用支持 API 37 的 Android Studio，安装 JDK 17 与 Android SDK 37。
2. 打开 `native/android`。
3. 同步 Gradle 后选择真机运行。

`VIBRATE` 不需要运行时授权。不同厂商的触觉原语支持不同，客户端会自动降级到平台预定义效果。

## 验证

仓库测试会校验跨端契约、传感器、触觉、静音默认值、断点恢复和服务端先锁定等关键实现标记。GitHub Actions 还会在 macOS 与 Ubuntu 上分别编译 iOS 模拟器和 Android Debug 包。
