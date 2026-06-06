"use client";

import { useEffect } from "react";

// 禁止触屏双指捏合缩放。viewport meta(user-scalable=no) 能挡住 Android，
// 但 iOS Safari 自 iOS 10 起会忽略它，必须用 JS 拦截：
//   - iOS Safari 捏合走 Safari 私有的 gesture* 事件
//   - 其它触屏走多指 touchmove
// 监听挂在 document 冒泡阶段，图表等组件的自身手势先处理，这里只 preventDefault
// 取消浏览器默认的页面缩放，不影响组件内部的触摸逻辑。
export function DisableZoom() {
  useEffect(() => {
    const preventGesture = (e: Event) => e.preventDefault();
    const preventMultiTouch = (e: TouchEvent) => {
      if (e.touches.length > 1) e.preventDefault();
    };

    const gestureEvents = ["gesturestart", "gesturechange", "gestureend"];
    gestureEvents.forEach((evt) => document.addEventListener(evt, preventGesture));
    document.addEventListener("touchmove", preventMultiTouch, { passive: false });

    return () => {
      gestureEvents.forEach((evt) => document.removeEventListener(evt, preventGesture));
      document.removeEventListener("touchmove", preventMultiTouch);
    };
  }, []);

  return null;
}
