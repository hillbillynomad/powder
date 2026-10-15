/**
 * Unit tests for the resort flyover helpers in powder/web/js/flyby.js (the real file)
 * and the tour data shipped in powder/web/tours/.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const WEB = path.resolve(__dirname, '../../../powder/web');
const source = fs.readFileSync(path.join(WEB, 'js/flyby.js'), 'utf8');

function loadFlyby() {
  const module = { exports: {} };
  new Function('module', source)(module);
  return module.exports;
}

const F = loadFlyby();

// A square loop: four waypoints, 10 s per leg
const square = {
  points: [
    { camera: [0, 0, 1000], target: [0, 1, 0], seconds: 10 },
    { camera: [1, 0, 1000], target: [1, 1, 0], seconds: 10 },
    { camera: [1, 1, 1000], target: [0, 1, 0], seconds: 10 },
    { camera: [0, 1, 1000], target: [0, 0, 0], seconds: 10 },
  ],
};

describe('slugify', () => {
  it('lowercases, strips accents and joins words with dashes', () => {
    expect(F.slugify('Snowbird')).toBe('snowbird');
    expect(F.slugify("Val d'Isère")).toBe('val-d-isere');
    expect(F.slugify('  Park City Mountain ')).toBe('park-city-mountain');
  });
});

describe('poseAt', () => {
  it('passes exactly through each waypoint at the start of its leg', () => {
    expect(F.tourDuration(square)).toBe(40);
    square.points.forEach((p, i) => {
      const pose = F.poseAt(square, i * 10);
      pose.camera.forEach((v, k) => expect(v).toBeCloseTo(p.camera[k], 9));
      pose.target.forEach((v, k) => expect(v).toBeCloseTo(p.target[k], 9));
    });
  });

  it('loops: the end of the last leg is the first waypoint again', () => {
    const end = F.poseAt(square, 40);
    const start = F.poseAt(square, 0);
    expect(end).toEqual(start);
    expect(F.poseAt(square, 45)).toEqual(F.poseAt(square, 5));
  });

  it('moves smoothly: no jumps between neighbouring moments, even across waypoints', () => {
    let prev = F.poseAt(square, 0).camera;
    for (let t = 0.1; t <= 40; t += 0.1) {
      const cur = F.poseAt(square, t).camera;
      expect(Math.hypot(cur[0] - prev[0], cur[1] - prev[1])).toBeLessThan(0.03);
      prev = cur;
    }
  });
});

describe('shipped tours', () => {
  const index = JSON.parse(fs.readFileSync(path.join(WEB, 'tours/index.json'), 'utf8'));
  const resorts = JSON.parse(fs.readFileSync(path.resolve(WEB, '../data/resorts.json'), 'utf8'));
  const names = new Set((resorts.resorts || resorts).map(r => F.slugify(r.name)));

  it.each(index.tours)('%s is a valid loop for a known resort', (slug) => {
    const tour = JSON.parse(fs.readFileSync(path.join(WEB, `tours/${slug}.json`), 'utf8'));
    expect(names.has(slug)).toBe(true);
    expect(F.slugify(tour.resort)).toBe(slug);
    expect(tour.points.length).toBeGreaterThanOrEqual(3);
    for (const p of tour.points) {
      expect(p.camera).toHaveLength(3);
      expect(p.target).toHaveLength(3);
      expect(p.seconds).toBeGreaterThan(0);
      expect(p.camera[2]).toBeGreaterThan(p.target[2]); // always looking down at the mountain
    }
  });
});
