// Tests the scroll animation maths. Run: node tests/engine_test.js
const assert = require("assert");
const S = require("../static/story.js");
const f = (a, b, n = 200) => Array.from({ length: n + 1 }, (_, i) => a + ((b - a) * i) / n);
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log("PASS " + name); };

test("scene 1 is fully visible at rest; later scenes wait hidden", () => {
  assert.deepStrictEqual(S.sceneState(0), { o: 1, s: 1, y: 0, r: 0 });
  for (const k of [1, 2, 3, 4, 5]) assert.strictEqual(S.sceneState(0 - k).o, 0);
});
test("exit: the scene visibly shrinks and recedes, monotonically", () => {
  const xs = f(S.HOLD, 1), st = xs.map(S.sceneState);
  for (let i = 1; i < st.length; i++) { assert(st[i].s <= st[i - 1].s + 1e-12); assert(st[i].o <= st[i - 1].o + 1e-12); }
  assert(Math.abs(st[0].s - 1) < 1e-9 && Math.abs(st[st.length - 1].s - 0.58) < 1e-9);
  assert(st.some(s => s.s < 0.8 && s.o > 0.5), "still readable while clearly smaller");
});
test("enter: the next scene grows from a smaller size into full view", () => {
  const st = f(-S.ENTER, 0).map(S.sceneState);
  for (let i = 1; i < st.length; i++) { assert(st[i].s >= st[i - 1].s - 1e-12); assert(st[i].o >= st[i - 1].o - 1e-12); }
  assert(Math.abs(st[0].s - 0.8) < 1e-9 && Math.abs(st[st.length - 1].s - 1) < 1e-9);
});
test("hand-over: while scene k exits, scene k+1 enters in sync", () => {
  for (const t of f(S.HOLD, 1)) {
    const a = S.sceneState(t), b = S.sceneState(t - 1);
    assert(a.o + b.o >= 1 - 1e-9, "never a blank frame at t=" + t);
  }
  const mid = (S.HOLD + 1) / 2, a = S.sceneState(mid), b = S.sceneState(mid - 1);
  assert(a.s < 1 && b.s < 1 && a.o > 0 && b.o > 0, "both visible mid-transition");
});
test("at most two scenes are ever visible, and one is fully in front when holding", () => {
  for (const t of f(0, 5 + S.TAIL, 700)) {
    const vis = [0, 1, 2, 3, 4, 5].filter(k => S.sceneState(t - k).o > 0.01);
    assert(vis.length >= 1 && vis.length <= 2, "t=" + t + " visible=" + vis);
  }
  for (let k = 0; k < 6; k++) for (const x of f(0, S.HOLD, 20)) assert.strictEqual(S.sceneState(x).o, 1);
});
test("last scene never exits before the sticky area ends", () => {
  assert(S.TAIL < S.HOLD);
  assert.strictEqual(S.sceneState(S.TAIL).o, 1);
});
test("lite mode (phones): panels grow in from below and ease out above, staying readable", () => {
  const vh = 800, h = 1400;
  let prev = S.liteState(vh + 50, h, vh);
  assert(prev.s <= 0.9 + 1e-9 && prev.o <= 0.35 + 1e-9, "starts small and dim below the fold");
  for (let vTop = vh; vTop >= 0; vTop -= 20) {           // scrolling down: the panel rises into view
    const st = S.liteState(vTop, h, vh);
    assert(st.s >= prev.s - 1e-12 && st.o >= prev.o - 1e-12, "grows monotonically at vTop=" + vTop);
    prev = st;
  }
  assert(Math.abs(prev.s - 1) < 1e-9 && Math.abs(prev.o - 1) < 1e-9, "full size once in view");
  const mid = S.liteState(-h / 2, h, vh);                // reading a tall panel: still full size
  assert(mid.s === 1 && mid.o === 1);
  const gone = S.liteState(-h, h, vh);                   // leaving at the top
  assert(gone.s >= 0.92 - 1e-9 && gone.o >= 0.5 - 1e-9, "never shrinks below 92% or fades below 50%");
  for (let vTop = 0; vTop >= -h; vTop -= 20) assert(S.liteState(vTop, h, vh).s >= 0.92 - 1e-9);
});
console.log(`\n${passed} engine tests passed`);
