# React Bits 源码组件

来源：https://github.com/DavidHDev/react-bits

引入时上游提交：`e12c22192ac7b4b452c5e2feb9b586d74765d696`。

- `SpotlightCard`：首页助手入口和菜品卡片的低强度鼠标柔光。
- `FadeContent`：路由页面的短淡入，保留 reduced-motion 分支。
- `CountUp`：看板真实数值的短过渡，保留格式化与减弱动态支持。

保留上游许可证 `LICENSE.md`。默认不开环境动画或重播。项目样式由包装组件调整，不向用户界面暴露库名。

适配：FadeContent 与 SpotlightCard 的最新 props 同步移到 effect，符合当前 React hooks 检查。
