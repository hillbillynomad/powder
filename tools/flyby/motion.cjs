// Camera motion audit for a tour: samples heading, bank (roll), pitch and altitude-above-ground
// every 0.25 s with the app's own functions and reports oscillation (sign flips of roll,
// heading reversals) and the fastest swings. usage: node tools/flyby/motion.cjs <slug>
const fs = require('fs');
const path = require('path');
const F = require('../../powder/web/js/flyby.js');
const tour = JSON.parse(fs.readFileSync(path.join(__dirname, '../../powder/web/tours', process.argv[2] + '.json'), 'utf8'));
const total = F.tourDuration(tour), dt = 0.25;
const rows = [];
for (let t = 0; t < total; t += dt) {
  const b = F.birdPose(tour, t);
  rows.push({ t, heading: b.bearing, roll: b.roll, pitch: b.pitch, alt: b.camera[2] });
}
let flips = 0, lastSign = 0, maxRollRate = 0, maxHeadRate = 0, maxPitchRate = 0;
const flipTimes = [];
for (let i = 1; i < rows.length; i++) {
  const a = rows[i - 1], b = rows[i];
  const s = Math.abs(b.roll) < 1 ? 0 : Math.sign(b.roll);
  if (s && lastSign && s !== lastSign) { flips++; flipTimes.push(+b.t.toFixed(1)); }
  if (s) lastSign = s;
  maxRollRate = Math.max(maxRollRate, Math.abs(b.roll - a.roll) / dt);
  maxHeadRate = Math.max(maxHeadRate, Math.abs(F.angleDiff(a.heading, b.heading)) / dt);
  maxPitchRate = Math.max(maxPitchRate, Math.abs(b.pitch - a.pitch) / dt);
}
console.log(`${process.argv[2]}: ${total.toFixed(0)} s, roll sign flips ${flips} (${(flips / total * 60).toFixed(1)}/min), max roll rate ${maxRollRate.toFixed(1)} deg/s, max heading rate ${maxHeadRate.toFixed(1)} deg/s, max pitch rate ${maxPitchRate.toFixed(1)} deg/s`);
if (flips) console.log('  roll flips at', flipTimes.slice(0, 30).join(', '));
