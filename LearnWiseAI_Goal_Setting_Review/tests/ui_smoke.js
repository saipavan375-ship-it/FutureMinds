// Optional browser-like test (simulated browser, not a real one). Needs Node.js and: npm install jsdom
// Start the app on port 5055 first:  python -c "import app; app.app.run(port=5055)"   then:  node tests/ui_smoke.js
const { JSDOM, VirtualConsole } = require("jsdom");
const BASE = process.env.BASE || "http://127.0.0.1:5055";
const wait = ms => new Promise(r => setTimeout(r, ms));
let failed = 0;
const check = (name, ok) => { if (!ok) failed++; console.log((ok ? "PASS " : "FAIL ") + name); };
async function open(user, opts = {}) {
  const errors = [], vc = new VirtualConsole();
  vc.on("jsdomError", e => errors.push(String(e.message || e)));
  const dom = await JSDOM.fromURL(BASE + "/", { runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      if (user) w.localStorage.setItem("lw_user", user);
      if (opts.simple) w.localStorage.setItem("lw_simple", "1");
      if (opts.width) w.innerWidth = opts.width;
      if (opts.reduce) w.matchMedia = q => ({ matches: /reduce/.test(q), addEventListener() {}, removeEventListener() {} });
      w.fetch = (u, o) => fetch(new URL(u, BASE), o);
      w.alert = m => errors.push("alert: " + m); w.confirm = () => true; w.scrollTo = () => {};
    } });
  await wait(1300);
  return { w: dom.window, d: dom.window.document, errors, txt: () => dom.window.document.getElementById("app").textContent.replace(/\s+/g, " ") };
}
(async () => {
  // ---- first visit: dashboard first, onboarding is an overlay on top ----
  const fv = await open(null);
  check("first visit: dashboard is visible behind the onboarding overlay", !!fv.d.getElementById("onb") && fv.d.querySelectorAll(".scene").length === 6 && /Welcome to LearnWise AI/.test(fv.txt()) && /Your Python journey starts here/.test(fv.txt()) && !/Loading/.test(fv.txt()));
  check("first visit shows honest zero states, no invented progress", /No quiz yet/.test(fv.txt()) && /0 learning activities in the last 7 days/.test(fv.txt()) && /No activity yet/.test(fv.txt()) && /Your plan appears after your first assessment/.test(fv.txt()) && /First goal:/.test(fv.txt()) && /Try a starter lesson/.test(fv.txt()));
  check("background is inert while the overlay is open", fv.d.getElementById("hdr").inert === true && fv.d.getElementById("app").inert === true && fv.d.getElementById("onbNick") === fv.d.activeElement);
  fv.d.getElementById("onbGo").click(); await wait(100);
  check("empty nickname is rejected politely", !!fv.d.getElementById("onb") && /nickname/i.test(fv.d.getElementById("onbErr").textContent));
  fv.d.getElementById("onbNick").value = "ab"; fv.d.getElementById("onbGo").click(); await wait(100);
  check("too-short nickname is rejected", !!fv.d.getElementById("onb") && /3 to 30/.test(fv.d.getElementById("onbErr").textContent));
  fv.d.getElementById("onbNick").value = "firstvisit"; fv.d.getElementById("onbGo").click(); await wait(1300);
  check("a valid nickname dismisses the overlay and personalises the dashboard", !fv.d.getElementById("onb") && fv.w.localStorage.getItem("lw_user") === "firstvisit" && /Welcome, firstvisit!/.test(fv.txt()) && fv.d.getElementById("hdr").inert === false);
  const rv = await open("firstvisit");
  check("returning visitor: no onboarding, personalised dashboard immediately", !rv.d.getElementById("onb") && /Welcome, firstvisit!/.test(rv.txt()));
  const sk = await open(null); sk.d.getElementById("onbSkip").click(); await wait(1300);
  const guestName = sk.w.localStorage.getItem("lw_user");
  check("skipping continues as a guest who can use the app", !sk.d.getElementById("onb") && /^guest-[a-f0-9]{6}$/.test(guestName) && /Welcome, Guest!/.test(sk.txt()) && /Guest/.test(sk.d.querySelector(".prof summary").textContent));
  sk.d.getElementById("newnick").value = "renamedguest"; await sk.w.renameUser(); await wait(1300);
  check("a guest can choose a nickname from the profile menu", sk.w.localStorage.getItem("lw_user") === "renamedguest" && /Learning as renamedguest/.test(sk.d.querySelector(".menu").textContent));
  const es = await open(null); es.d.getElementById("onb").dispatchEvent(new es.w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await wait(1300);
  check("Escape never traps the visitor (continues as guest)", !es.d.getElementById("onb") && /^guest-/.test(es.w.localStorage.getItem("lw_user")));
  const s = await open("jsdomtest"), { w, d, txt } = s;
  check("new learner sees welcome and real empty states", /Welcome, jsdomtest/.test(txt()) && /Your plan appears after your first assessment/.test(txt()) && /No activity yet/.test(txt()) && /No quiz yet/.test(txt()));
  check("dashboard has the six scenes and the scroll dots", d.querySelectorAll(".scene").length === 6 && d.querySelectorAll(".dots button").length === 6);
  // ---- scroll engine wiring (layout is simulated: jsdom has no real scrolling) ----
  const story = d.getElementById("story"), sc = [...d.querySelectorAll(".scene")], slot = w.innerHeight;
  let top = 0; story.getBoundingClientRect = () => ({ top });
  const scrollTo = async t => { top = -t * slot; w.dispatchEvent(new w.Event("scroll")); await wait(900); };
  const scale = e => +(e.style.transform.match(/scale\(([\d.]+)\)/) || [])[1], op = e => +e.style.opacity;
  check("cinematic mode is on for a large screen", story.classList.contains("cine") && story.classList.contains("js"));
  check("at the top only the dashboard is shown", op(sc[0]) === 1 && scale(sc[0]) === 1 && sc[1].style.visibility === "hidden" && sc[0].inert === false && sc[1].inert === true);
  await scrollTo(0.8);
  check("mid-scroll: dashboard shrinks and recedes while the next scene grows in", scale(sc[0]) < 0.9 && scale(sc[0]) > 0.6 && op(sc[0]) > 0.3 && op(sc[1]) > 0.5 && scale(sc[1]) > 0.8 && scale(sc[1]) < 1);
  check("mid-scroll: the next scene sits behind the shrinking dashboard", +w.getComputedStyle(sc[0]).zIndex > +w.getComputedStyle(sc[1]).zIndex);
  await scrollTo(1.15);
  check("after the transition the next scene is full size and the dashboard is gone", Math.abs(scale(sc[1]) - 1) < 0.01 && op(sc[1]) === 1 && sc[0].style.visibility === "hidden" && sc[1].inert === false);
  await scrollTo(0.8);
  await scrollTo(0);
  check("scrolling back up restores the dashboard", scale(sc[0]) === 1 && op(sc[0]) === 1 && sc[1].style.visibility === "hidden");
  await scrollTo(5.6);
  check("the last scene is reachable and fully visible", op(sc[5]) === 1 && Math.abs(scale(sc[5]) - 1) < 0.01);
  await scrollTo(0);
  // ---- learner journey through the real backend ----
  w.begin(); await wait(800);
  check("quiz starts with a counter", /Question 1 of 24/.test(txt()));
  for (let n = 0; n < 24; n++) { w.pick(n % 2); w.move(1); await wait(5); }
  await wait(100); check("review screen before submit", /Review your answers/.test(txt()));
  await w.submit(); await wait(1200);
  check("results page with summary and answer review", /Overall score/.test(txt()) && /What this suggests/.test(txt()) && /Review all 24 answers/.test(txt()));
  w.go("dash"); await wait(1300);
  check("dashboard shows the real quiz score and Continue Learning", /of 24 correct/.test(txt()) && !!d.getElementById("continueBtn") && /Continue Learning/.test(txt()) && /Level 1/.test(txt()) && /Earned: First assessment/.test(txt()));
  check("weekly chart counts real activity and the plan timeline is filled", /1 learning activity in the last 7 days/.test(txt()) && /Day 1:/.test(txt()));
  check("featured practice challenge is connected to the existing module", /Practice Python:/.test(txt()) && /Challenge:/.test(txt()) && d.querySelectorAll(".scene.s4 pre.code .k, .scene.s4 pre.code .s").length > 0);
  const m = d.getElementById("continueBtn").getAttribute("onclick").match(/openModule\('(\w+)'\)/);
  check("Continue Learning opens a real module", !!m);
  const ids = [...d.querySelectorAll(".scene.s4 [id^=st_]")].map(e => e.id.slice(3));
  for (let k = 0; k < 4 && d.getElementById("st_" + ids[0]).textContent !== "Solved"; k++) { await w.answerItem(ids[0], k); await wait(300); }
  check("the dashboard challenge accepts answers and gives feedback", d.getElementById("st_" + ids[0]).textContent === "Solved" && d.getElementById("fb_" + ids[0]).textContent.length > 30);
  w.openModule(m ? m[1] : "var"); await wait(900);
  check("module page works (explanation, code, practice)", /The idea/.test(txt()) && /Practice 1/.test(txt()) && d.querySelectorAll("pre.code .k, pre.code .s, pre.code .n").length > 0);
  w.go("plan"); await wait(900);
  const cb = d.querySelector("input[type=checkbox]"); cb.checked = true; cb.dispatchEvent(new w.Event("change")); await wait(1000);
  check("study task completion persists in the plan", !!d.querySelector(".task.done"));
  w.go("dash"); await wait(1300);
  check("dashboard reflects the finished task, practice and activity", /Study tasks done: 1 of/.test(txt()) && /Completed study task/.test(txt()) && /Solved a practice item/.test(txt()));
  for (const v of ["learn", "assess", "progress"]) { w.go(v); await wait(800); }
  check("Learn, Assessments and My Progress still work", /Attempt history/.test(txt()));
  w.toggleRewards(false); await wait(300); w.go("dash"); await wait(1300);
  check("rewards can be hidden", !/Current streak/.test(txt()) && /Rewards are hidden/.test(txt()));
  w.toggleRewards(true);
  // ---- refresh, simple view, small screen, reduced motion ----
  const r2 = await open("jsdomtest");
  check("after a refresh the progress is still there", /Welcome back, jsdomtest/.test(r2.txt()) && /of 24 correct/.test(r2.txt()));
  const r3 = await open("jsdomtest", { simple: true });
  check("Simple view turns the zoom effect off but keeps all content", !r3.d.getElementById("story").classList.contains("cine") && r3.d.querySelectorAll(".scene").length === 6 && !r3.d.querySelector(".scene[style]"));
  const r4 = await open("jsdomtest", { width: 500 });
  const st4 = r4.d.getElementById("story");
  check("phones and tablets get the lighter zoom (content stays full size)", st4.classList.contains("lite") && !st4.classList.contains("cine") && r4.d.querySelectorAll(".scene .panel[style*=scale]").length === 6 && !r4.d.querySelector(".scene[style]"));
  const r5 = await open("jsdomtest", { reduce: true }), st5 = r5.d.getElementById("story");
  check("reduced motion gets the plain layout with no scroll animation", !st5.classList.contains("cine") && !st5.classList.contains("lite") && !r5.d.querySelector(".panel[style]"));
  const g = await open(null); g.d.getElementById("onbSkip").click(); await wait(1300);
  g.d.getElementById("newnick").value = "jsdomtest"; await g.w.renameUser(); await wait(500);
  check("renaming never merges into an existing learner's history", /already has learning history/.test(g.d.getElementById("renmsg").textContent) && /^guest-/.test(g.w.localStorage.getItem("lw_user")));
  const errs = [...fv.errors, ...rv.errors, ...sk.errors, ...es.errors, ...g.errors, ...s.errors, ...r2.errors, ...r3.errors, ...r4.errors, ...r5.errors];
  console.log("page errors:", errs.length ? errs : "none");
  process.exit(failed || errs.length ? 1 : 0);
})().catch(e => { console.log("SCRIPT ERROR", e); process.exit(1); });
