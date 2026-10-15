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

describe('bird mode', () => {
  // Same square loop without targets: the camera must face the way it flies
  const bird = { points: square.points.map(({ camera, seconds }) => ({ camera, seconds, pitch: 60 })) };

  it('faces the direction of travel', () => {
    // Middle of the first leg runs east (0,0) -> (1,0); the third runs west. Within 10 degrees:
    // the heading already leans toward the next corner, like a bird anticipating a turn.
    expect(Math.abs(F.angleDiff(F.birdPose(bird, 5).bearing, 90))).toBeLessThan(10);
    expect(Math.abs(F.angleDiff(F.birdPose(bird, 25).bearing, 270))).toBeLessThan(10);
  });

  it('uses the waypoint pitch and banks into turns, but never past the limit', () => {
    let maxRoll = 0;
    for (let t = 0; t < 40; t += 0.5) {
      const p = F.birdPose(bird, t);
      expect(p.pitch).toBeCloseTo(60, 6);
      maxRoll = Math.max(maxRoll, Math.abs(p.roll));
    }
    expect(maxRoll).toBeGreaterThan(1);
    expect(maxRoll).toBeLessThanOrEqual(10);
  });

  it('lookPoint aims along the line of sight: ahead on the heading and down by the pitch', () => {
    const [lng, lat, alt] = F.lookPoint([0, 0, 1000], 90, 60, 1000); // east, 30 degrees below level
    expect(lat).toBeCloseTo(0, 9);
    expect(lng * 111320).toBeCloseTo(1000 * Math.sin(Math.PI / 3), 3);
    expect(alt).toBeCloseTo(1000 - 1000 * Math.cos(Math.PI / 3), 6);
  });

  it('blends authored ground heights along the loop', () => {
    const grounded = { points: bird.points.map((p, i) => ({ ...p, ground: 100 * (i + 1) })) };
    expect(F.birdPose(grounded, 0).ground).toBeCloseTo(100, 6);
    expect(F.birdPose(grounded, 10).ground).toBeCloseTo(200, 6);
    expect(F.birdPose(bird, 0).ground).toBeUndefined();
  });

  it('angleDiff takes the short way round', () => {
    expect(F.angleDiff(350, 10)).toBe(20);
    expect(F.angleDiff(10, 350)).toBe(-20);
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
      expect(p.seconds).toBeGreaterThan(0);
      if (p.target) expect(p.camera[2]).toBeGreaterThan(p.target[2]); // look-at: always looking down
      else expect(p.pitch ?? 68).toBeLessThan(80); // bird: tilted down, never at the horizon
    }
  });
});

describe('orbitWeight (bird flight with orbit points)', () => {
  const cam = (i) => [i, 0, 100];
  const tour = {
    points: [
      { camera: cam(0), seconds: 10, target: [0, 0, 0] },
      { camera: cam(1), seconds: 10, target: [0, 0, 0], orbit: 1 },
      { camera: cam(2), seconds: 10, target: [0, 0, 0], orbit: 1 },
      { camera: cam(3), seconds: 10, target: [0, 0, 0] },
    ],
  };

  it('is 0 on a bird leg, 1 on an orbit leg, and eases between them', () => {
    expect(F.orbitWeight(tour, 0)).toBe(0);
    expect(F.orbitWeight(tour, 5)).toBeCloseTo(0.5, 5);
    expect(F.orbitWeight(tour, 10)).toBe(1);
    expect(F.orbitWeight(tour, 15)).toBe(1);
    expect(F.orbitWeight(tour, 25)).toBeCloseTo(0.5, 5);
    expect(F.orbitWeight(tour, 40)).toBe(0); // wraps
  });
});
