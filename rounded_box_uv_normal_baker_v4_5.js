/*
Rounded Box UV Normal Baker for Blockbench 5
Version: 4.5.0

Adds improved alpha-guided baking behavior:
- Transparent/cutout parts of the texture can suppress the box-baked normals
- Opaque pixels near alpha edges follow the texture silhouette more closely
- Flat normal-color background is back by default (opaque 128,128,255 background)
- Surface normals from the color texture are layered over the baked normals
*/

(function() {
  const PLUGIN_ID = 'rounded_box_uv_normal_baker_v4_5';
  let bakeAction;
  const FACE_NAMES = ['north', 'east', 'south', 'west', 'up', 'down'];
  const FACE_AXES = {
    north: { flipX: false, flipY: false },
    south: { flipX: true,  flipY: false },
    east:  { flipX: false, flipY: false },
    west:  { flipX: true,  flipY: false },
    up:    { flipX: false, flipY: true  },
    down:  { flipX: false, flipY: false }
  };

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function safeNumber(v, fallback) {
    v = Number(v);
    return Number.isFinite(v) ? v : fallback;
  }
  function smoothstep(t) {
    t = clamp(t, 0, 1);
    return t * t * (3 - 2 * t);
  }
  function normalize3(x, y, z) {
    const l = Math.hypot(x, y, z);
    if (!l) return [0, 0, 1];
    return [x / l, y / l, z / l];
  }

  function getOutputTextureSize(fallback, sizeMode) {
    fallback = Math.max(1, Math.round(safeNumber(fallback, 128)));
    if (sizeMode === 'manual') return { w: fallback, h: fallback };
    if (sizeMode === 'selected') {
      try {
        if (Texture && Texture.selected && Texture.selected.img) {
          const img = Texture.selected.img;
          const w = img.naturalWidth || img.width;
          const h = img.naturalHeight || img.height;
          if (w && h) return { w, h };
        }
      } catch (e) {}
    }
    if (sizeMode === 'project') {
      try {
        if (Project && Project.texture_width && Project.texture_height) {
          return { w: Project.texture_width, h: Project.texture_height };
        }
      } catch (e) {}
    }
    return { w: fallback, h: fallback };
  }

  function getSourceUvTextureSize() {
    try {
      if (Project && Project.texture_width && Project.texture_height) {
        return {
          w: Math.max(1, Math.round(Project.texture_width)),
          h: Math.max(1, Math.round(Project.texture_height))
        };
      }
    } catch (e) {}
    try {
      if (Texture && Texture.selected && Texture.selected.img) {
        const img = Texture.selected.img;
        const w = img.naturalWidth || img.width;
        const h = img.naturalHeight || img.height;
        if (w && h) return { w, h };
      }
    } catch (e) {}
    return { w: 16, h: 16 };
  }

  function getSelectedTextureUuid() {
    try {
      if (Texture && Texture.selected) return Texture.selected.uuid || Texture.selected.id || null;
    } catch (e) {}
    return null;
  }

  function faceUsesSelectedTexture(face, selectedUuid) {
    if (!selectedUuid) return true;
    if (!face) return false;
    try {
      if (face.texture === selectedUuid) return true;
      if (face.texture && face.texture.uuid === selectedUuid) return true;
      if (typeof face.getTexture === 'function') {
        const tex = face.getTexture();
        if (tex && (tex.uuid === selectedUuid || tex.id === selectedUuid)) return true;
      }
    } catch (e) {}
    return false;
  }

  function isFaceTextured(face) {
    if (!face) return false;
    return !(face.texture === false || face.texture === null || face.texture === undefined);
  }

  function getTextureForFace(face) {
    try {
      if (face && typeof face.getTexture === 'function') {
        const tex = face.getTexture();
        if (tex) return tex;
      }
    } catch (e) {}
    try {
      return Texture && Texture.selected ? Texture.selected : null;
    } catch (e) {}
    return null;
  }

  function rectFromNumbersRaw(ax, ay, bx, by, maxW, maxH) {
    if (![ax, ay, bx, by].every(Number.isFinite)) return null;
    let x0 = Math.min(ax, bx), x1 = Math.max(ax, bx);
    let y0 = Math.min(ay, by), y1 = Math.max(ay, by);
    if (x1 <= 1.0001 && y1 <= 1.0001) {
      x0 *= maxW; x1 *= maxW; y0 *= maxH; y1 *= maxH;
    }
    x0 = clamp(x0, 0, maxW); x1 = clamp(x1, 0, maxW);
    y0 = clamp(y0, 0, maxH); y1 = clamp(y1, 0, maxH);
    if ((x1 - x0) < 0.001 || (y1 - y0) < 0.001) return null;
    return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 };
  }

  function scaleRect(rect, srcW, srcH, outW, outH) {
    if (!rect) return null;
    return {
      x0: rect.x0 * outW / Math.max(1, srcW),
      y0: rect.y0 * outH / Math.max(1, srcH),
      x1: rect.x1 * outW / Math.max(1, srcW),
      y1: rect.y1 * outH / Math.max(1, srcH),
      w: rect.w * outW / Math.max(1, srcW),
      h: rect.h * outH / Math.max(1, srcH)
    };
  }

  function getFaceUvRects(face, srcW, srcH, outW, outH) {
    let srcRect = null;
    try {
      if (face && typeof face.getBoundingRect === 'function') {
        const r = face.getBoundingRect();
        if (r) {
          let ax = safeNumber(r.ax, NaN), ay = safeNumber(r.ay, NaN);
          let bx = safeNumber(r.bx, NaN), by = safeNumber(r.by, NaN);
          if (!Number.isFinite(ax) && Number.isFinite(r.x)) ax = r.x;
          if (!Number.isFinite(ay) && Number.isFinite(r.y)) ay = r.y;
          if (!Number.isFinite(bx) && Number.isFinite(r.x) && Number.isFinite(r.w)) bx = r.x + r.w;
          if (!Number.isFinite(by) && Number.isFinite(r.y) && Number.isFinite(r.h)) by = r.y + r.h;
          srcRect = rectFromNumbersRaw(ax, ay, bx, by, srcW, srcH);
        }
      }
    } catch (e) {}
    if (!srcRect) {
      try {
        const uv = face && face.uv;
        if (Array.isArray(uv) && uv.length >= 4) {
          srcRect = rectFromNumbersRaw(
            safeNumber(uv[0], NaN), safeNumber(uv[1], NaN),
            safeNumber(uv[2], NaN), safeNumber(uv[3], NaN),
            srcW, srcH
          );
        }
      } catch (e) {}
    }
    if (!srcRect) return null;
    return { src: srcRect, out: scaleRect(srcRect, srcW, srcH, outW, outH) };
  }

  function cubeSize(cube) {
    let sx = 16, sy = 16, sz = 16;
    try {
      sx = Math.abs(cube.to[0] - cube.from[0]) || 16;
      sy = Math.abs(cube.to[1] - cube.from[1]) || 16;
      sz = Math.abs(cube.to[2] - cube.from[2]) || 16;
    } catch (e) {}
    return { sx, sy, sz };
  }

  function physicalFaceSize(cube, faceName) {
    const s = cubeSize(cube);
    switch (faceName) {
      case 'north':
      case 'south': return { u: s.sx, v: s.sy };
      case 'east':
      case 'west':  return { u: s.sz, v: s.sy };
      case 'up':
      case 'down':  return { u: s.sx, v: s.sz };
      default:      return { u: s.sx, v: s.sy };
    }
  }

  function getBakeCubes(selectedOnly) {
    const result = [];
    try {
      Cube.all.forEach(cube => {
        if (!cube || !cube.faces) return;
        if (selectedOnly && !cube.selected) return;
        result.push(cube);
      });
    } catch (e) {}
    return result;
  }

  function edgeSignedDistance01(t, radius) {
    let d = 0;
    if (t < radius) d = -(1 - t / radius);
    else if (t > 1 - radius) d = 1 - (1 - t) / radius;
    return Math.sign(d) * smoothstep(Math.abs(d));
  }

  function roundedFaceNormal(localU, localV, radiusU, radiusV, strength, faceName, flipGreen) {
    const axes = FACE_AXES[faceName] || FACE_AXES.north;
    let nx = edgeSignedDistance01(localU, radiusU);
    let ny = edgeSignedDistance01(localV, radiusV);
    if (axes.flipX) nx = -nx;
    if (axes.flipY) ny = -ny;
    nx *= strength;
    ny *= strength;
    if (flipGreen) ny = -ny;
    const len2 = nx * nx + ny * ny;
    if (len2 > 0.998) {
      const s = Math.sqrt(0.998 / len2);
      nx *= s; ny *= s;
    }
    const nz = Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny));
    return normalize3(nx, ny, nz);
  }

  const textureSamplerCache = {};

  function getTextureKey(tex) {
    if (!tex) return null;
    return tex.uuid || tex.id || tex.name || null;
  }

  function getTextureSampler(tex) {
    const key = getTextureKey(tex);
    if (!key) return null;
    if (textureSamplerCache[key]) return textureSamplerCache[key];
    try {
      const img = tex.img || tex.image || null;
      if (!img) return null;
      const w = img.naturalWidth || img.width;
      const h = img.naturalHeight || img.height;
      if (!w || !h) return null;
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      const data = ctx.getImageData(0, 0, w, h).data;
      const sampler = { w, h, data };
      textureSamplerCache[key] = sampler;
      return sampler;
    } catch (e) {
      console.warn('Could not read texture sampler:', e);
      return null;
    }
  }

  function bilinearRGBA(sampler, x, y) {
    if (!sampler) return [1, 1, 1, 1];
    const w = sampler.w, h = sampler.h, data = sampler.data;
    x = clamp(x, 0, w - 1);
    y = clamp(y, 0, h - 1);
    const x0 = Math.floor(x), y0 = Math.floor(y);
    const x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1);
    const tx = x - x0, ty = y - y0;
    function rgba(ix, iy) {
      const idx = (iy * w + ix) * 4;
      return [data[idx]/255, data[idx+1]/255, data[idx+2]/255, data[idx+3]/255];
    }
    const c00 = rgba(x0, y0), c10 = rgba(x1, y0), c01 = rgba(x0, y1), c11 = rgba(x1, y1);
    const out = [0,0,0,0];
    for (let i=0;i<4;i++) out[i] = lerp(lerp(c00[i], c10[i], tx), lerp(c01[i], c11[i], tx), ty);
    return out;
  }

  function bilinearAlpha(sampler, x, y) {
    return bilinearRGBA(sampler, x, y)[3];
  }

  function luminanceFromRGBA(rgba) {
    return rgba[0] * 0.2126 + rgba[1] * 0.7152 + rgba[2] * 0.0722;
  }

  function alphaNeighborhoodMask(sampler, srcX, srcY, threshold, sampleStep) {
    if (!sampler) return 1;
    const s = Math.max(0.5, sampleStep || 1);
    const aC = bilinearAlpha(sampler, srcX, srcY);
    const aL = bilinearAlpha(sampler, srcX - s, srcY);
    const aR = bilinearAlpha(sampler, srcX + s, srcY);
    const aU = bilinearAlpha(sampler, srcX, srcY - s);
    const aD = bilinearAlpha(sampler, srcX, srcY + s);
    const avg = (aC + aL + aR + aU + aD) / 5;
    return smoothstep((avg - threshold) / Math.max(0.0001, 1 - threshold));
  }

  function computeAlphaNormalAdd(sampler, srcX, srcY, flipGreen, strength, sampleStep) {
    if (!sampler || strength <= 0) return [0, 0];
    const s = Math.max(0.5, sampleStep || 1);
    const ax0 = bilinearAlpha(sampler, srcX - s, srcY);
    const ax1 = bilinearAlpha(sampler, srcX + s, srcY);
    const ay0 = bilinearAlpha(sampler, srcX, srcY - s);
    const ay1 = bilinearAlpha(sampler, srcX, srcY + s);
    let gx = ax1 - ax0;
    let gy = ay1 - ay0;
    let nx = -gx * strength;
    let ny = -gy * strength;
    if (flipGreen) ny = -ny;
    return [nx, ny];
  }

  function computeSurfaceNormalAdd(sampler, srcX, srcY, flipGreen, strength, sampleStep, invertHeight, alphaAware, alphaThreshold) {
    if (!sampler || strength <= 0) return [0, 0];
    const s = Math.max(0.25, sampleStep || 1);
    const cL = bilinearRGBA(sampler, srcX - s, srcY);
    const cR = bilinearRGBA(sampler, srcX + s, srcY);
    const cU = bilinearRGBA(sampler, srcX, srcY - s);
    const cD = bilinearRGBA(sampler, srcX, srcY + s);
    function sampleHeight(c) {
      let h = luminanceFromRGBA(c);
      if (alphaAware && c[3] < alphaThreshold) return null;
      return h;
    }
    let hL = sampleHeight(cL), hR = sampleHeight(cR), hU = sampleHeight(cU), hD = sampleHeight(cD);
    const cC = bilinearRGBA(sampler, srcX, srcY);
    const hC = luminanceFromRGBA(cC);
    if (hL === null) hL = hC;
    if (hR === null) hR = hC;
    if (hU === null) hU = hC;
    if (hD === null) hD = hC;
    let gx = hR - hL;
    let gy = hD - hU;
    if (invertHeight) { gx = -gx; gy = -gy; }
    let nx = -gx * strength;
    let ny = -gy * strength;
    if (flipGreen) ny = -ny;
    return [nx, ny];
  }

  function bake(options) {
    for (const k in textureSamplerCache) delete textureSamplerCache[k];

    const outSize = getOutputTextureSize(options.fallbackSize, options.sizeMode);
    const srcSize = getSourceUvTextureSize();
    const texW = Math.max(1, Math.round(outSize.w));
    const texH = Math.max(1, Math.round(outSize.h));
    const srcW = Math.max(1, Math.round(srcSize.w));
    const srcH = Math.max(1, Math.round(srcSize.h));

    const accum = new Float32Array(texW * texH * 3);
    const weight = new Float32Array(texW * texH);
    const coverage = new Uint8Array(texW * texH);
    const outAlpha = new Uint8Array(texW * texH);

    const selectedTextureUuid = getSelectedTextureUuid();
    const cubes = getBakeCubes(options.selectedOnly);

    let usedCubeCount = 0;
    let usedFaceCount = 0;
    const debugRows = [];

    cubes.forEach(cube => {
      let cubeHadFace = false;
      FACE_NAMES.forEach(faceName => {
        const face = cube.faces[faceName];
        if (!face) return;
        if (!options.includeUntextured && !isFaceTextured(face)) return;
        if (options.onlySelectedTexture && !faceUsesSelectedTexture(face, selectedTextureUuid)) return;

        const rects = getFaceUvRects(face, srcW, srcH, texW, texH);
        if (!rects) return;
        const srcRect = rects.src;
        const outRect = rects.out;

        const faceTexture = getTextureForFace(face);
        const textureSampler = getTextureSampler(faceTexture);
        const alphaSampler = options.useAlphaCutout ? textureSampler : null;
        const surfaceSampler = options.generateSurfaceNormals ? textureSampler : null;

        const phys = physicalFaceSize(cube, faceName);
        const minPhys = Math.max(0.001, Math.min(phys.u, phys.v));
        let r = options.radiusModelUnits / minPhys;
        r = clamp(r, 0.001, 0.49);

        const x0 = clamp(Math.floor(outRect.x0) - options.padding, 0, texW - 1);
        const x1 = clamp(Math.ceil(outRect.x1) + options.padding, 0, texW);
        const y0 = clamp(Math.floor(outRect.y0) - options.padding, 0, texH - 1);
        const y1 = clamp(Math.ceil(outRect.y1) + options.padding, 0, texH);

        const srcStepX = srcRect.w / Math.max(1, outRect.w);
        const srcStepY = srcRect.h / Math.max(1, outRect.h);
        const alphaStep = Math.max(0.5, Math.min(2.0, Math.max(srcStepX, srcStepY)));
        const surfaceStep = Math.max(0.25, options.surfaceSampleRadius * Math.max(srcStepX, srcStepY));

        for (let y = y0; y < y1; y++) {
          for (let x = x0; x < x1; x++) {
            const px = x + 0.5, py = y + 0.5;
            const inside = px >= outRect.x0 && px <= outRect.x1 && py >= outRect.y0 && py <= outRect.y1;
            if (!inside && !options.bleedPadding) continue;

            const sampleX = clamp(px, outRect.x0, outRect.x1);
            const sampleY = clamp(py, outRect.y0, outRect.y1);
            const u = clamp((sampleX - outRect.x0) / outRect.w, 0, 1);
            const v = clamp((sampleY - outRect.y0) / outRect.h, 0, 1);
            const srcX = srcRect.x0 + u * srcRect.w;
            const srcY = srcRect.y0 + v * srcRect.h;
            const alpha = alphaSampler ? bilinearAlpha(alphaSampler, srcX, srcY) : 1;

            const idx = y * texW + x;
            if (options.preserveTextureAlpha) {
              outAlpha[idx] = Math.max(outAlpha[idx], Math.round(alpha * 255));
            }

            if (options.useAlphaCutout && alpha < options.alphaThreshold) {
              continue;
            }

            let n = roundedFaceNormal(u, v, r, r, options.strength, faceName, options.flipGreen);

            if (options.useAlphaCutout && options.alphaGuidedBake && alphaSampler) {
              const mask = alphaNeighborhoodMask(alphaSampler, srcX, srcY, options.alphaThreshold, alphaStep);
              n = normalize3(lerp(0, n[0], mask), lerp(0, n[1], mask), lerp(1, n[2], mask));
            }

            if (options.useAlphaCutout && alphaSampler) {
              const addAlpha = computeAlphaNormalAdd(alphaSampler, srcX, srcY, options.flipGreen, options.alphaEdgeStrength, alphaStep);
              n = normalize3(n[0] + addAlpha[0], n[1] + addAlpha[1], n[2]);
            }

            if (options.generateSurfaceNormals && surfaceSampler) {
              const addSurface = computeSurfaceNormalAdd(
                surfaceSampler,
                srcX,
                srcY,
                options.flipGreen,
                options.surfaceStrength,
                surfaceStep,
                options.invertSurfaceHeight,
                options.useAlphaCutout,
                options.alphaThreshold
              );
              n = normalize3(n[0] + addSurface[0], n[1] + addSurface[1], n[2]);
            }

            const w = inside ? 1 : 0.35;
            accum[idx * 3 + 0] += n[0] * w;
            accum[idx * 3 + 1] += n[1] * w;
            accum[idx * 3 + 2] += n[2] * w;
            weight[idx] += w;
            coverage[idx] = 1;
          }
        }

        usedFaceCount++;
        cubeHadFace = true;
        debugRows.push({ cube: cube.name || '(cube)', face: faceName, rect: [outRect.x0.toFixed(2), outRect.y0.toFixed(2), outRect.x1.toFixed(2), outRect.y1.toFixed(2)].join(', ') });
      });
      if (cubeHadFace) usedCubeCount++;
    });

    if (!usedFaceCount) {
      throw new Error('No usable cube faces were found. Make sure the model uses cube elements with box UV or rectangular face UVs.');
    }

    const canvas = document.createElement('canvas');
    canvas.width = texW;
    canvas.height = texH;
    const ctx = canvas.getContext('2d');
    const image = ctx.createImageData(texW, texH);
    const data = image.data;

    for (let i = 0; i < texW * texH; i++) {
      let nx = 0, ny = 0, nz = 1;
      if (weight[i] > 0) {
        const n = normalize3(
          accum[i * 3 + 0] / weight[i],
          accum[i * 3 + 1] / weight[i],
          accum[i * 3 + 2] / weight[i]
        );
        nx = n[0]; ny = n[1]; nz = n[2];
      }
      data[i * 4 + 0] = Math.round((nx * 0.5 + 0.5) * 255);
      data[i * 4 + 1] = Math.round((ny * 0.5 + 0.5) * 255);
      data[i * 4 + 2] = Math.round((nz * 0.5 + 0.5) * 255);
      if (options.preserveTextureAlpha) {
        data[i * 4 + 3] = options.transparentUnused && !coverage[i] ? 0 : outAlpha[i];
      } else {
        data[i * 4 + 3] = 255;
      }
    }

    ctx.putImageData(image, 0, 0);
    return { canvas, texW, texH, srcW, srcH, usedCubeCount, usedFaceCount, debugRows };
  }

  function addTexture(canvas, filename) {
    try {
      const url = canvas.toDataURL('image/png');
      const tex = new Texture({ name: filename, source: url }).add(false);
      if (typeof tex.fromDataURL === 'function') tex.fromDataURL(url);
      tex.select();
      return true;
    } catch (e) {
      console.error(e);
      return false;
    }
  }

  function canvasToBlob(canvas, cb) {
    try {
      canvas.toBlob(blob => {
        if (!blob) cb(new Error('Failed to create PNG blob.'));
        else cb(null, blob);
      }, 'image/png');
    } catch (e) { cb(e); }
  }

  function saveWithBlobDownload(canvas, filename) {
    canvasToBlob(canvas, (err, blob) => {
      if (err) { Blockbench.showQuickMessage(err.message, 4000); return; }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.rel = 'noopener'; a.style.display = 'none';
      document.body.appendChild(a); a.click();
      setTimeout(() => {
        try { document.body.removeChild(a); } catch (e) {}
        try { URL.revokeObjectURL(url); } catch (e) {}
      }, 1500);
    });
  }

  function saveWithNativePicker(canvas, filename) {
    try {
      if (typeof require !== 'function' || typeof Blockbench.pickDirectory !== 'function') return false;
      const fs = require('fs');
      const path = require('path');
      Blockbench.pickDirectory({ title: 'Choose output folder' }, folder => {
        if (!folder) return;
        canvasToBlob(canvas, (err, blob) => {
          if (err) { Blockbench.showQuickMessage(err.message, 4000); return; }
          const reader = new FileReader();
          reader.onload = () => {
            try {
              const outPath = path.join(folder, filename);
              fs.writeFileSync(outPath, Buffer.from(reader.result));
              Blockbench.showQuickMessage('Saved ' + filename, 3500);
            } catch (e) {
              console.error(e);
              Blockbench.showQuickMessage('Save failed: ' + e.message, 5000);
            }
          };
          reader.onerror = () => Blockbench.showQuickMessage('Could not read PNG blob.', 4000);
          reader.readAsArrayBuffer(blob);
        });
      });
      return true;
    } catch (e) {
      console.warn(e);
      return false;
    }
  }

  function showDebug(result) {
    const rows = result.debugRows.slice(0, 100).map(r => `${r.cube} / ${r.face}: ${r.rect}`).join('\n');
    Blockbench.showMessageBox({
      title: 'Rounded Normal Bake Debug',
      message:
        `Source UV space: ${result.srcW}×${result.srcH}\n` +
        `Output texture: ${result.texW}×${result.texH}\n` +
        `Cubes used: ${result.usedCubeCount}\n` +
        `Faces baked: ${result.usedFaceCount}\n\n` +
        `Scaled UV face rectangles:\n${rows}` +
        (result.debugRows.length > 100 ? '\n...' : '')
    });
  }

  function openDialog() {
    const projectName = (Project && Project.name ? Project.name.replace(/\.[^.]+$/, '') : 'model');
    const defaultFilename = projectName + '_n.png';
    const dialog = new Dialog({
      id: 'rounded_box_uv_normal_baker_dialog_v4_5',
      title: 'Bake Rounded Box UV Normal Map',
      width: 620,
      form: {
        filename: { label: 'Output filename', type: 'text', value: defaultFilename },
        size_mode: {
          label: 'Texture size source', type: 'select', value: 'manual',
          options: { manual: 'Manual size below', selected: 'Selected texture size', project: 'Project texture size' }
        },
        fallback_size: { label: 'Manual texture size', type: 'number', value: 128, min: 16, max: 4096, step: 16 },
        radius: { label: 'Round radius in model units', type: 'number', value: 1, min: 0.01, max: 16, step: 0.05 },
        strength: { label: 'Box-edge normal strength', type: 'number', value: 0.8, min: 0.01, max: 2, step: 0.05 },

        generate_surface_normals: { label: 'Generate surface normals from color texture', type: 'checkbox', value: true },
        surface_strength: { label: 'Surface normal strength', type: 'number', value: 1.0, min: 0, max: 8, step: 0.05 },
        surface_sample_radius: { label: 'Surface sample radius', type: 'number', value: 1.0, min: 0.25, max: 8, step: 0.25 },
        invert_surface_height: { label: 'Invert surface height', type: 'checkbox', value: false },

        use_alpha_cutout: { label: 'Use texture alpha as cutout mask', type: 'checkbox', value: true },
        alpha_guided_bake: { label: 'Let texture alpha shape baked normals', type: 'checkbox', value: true },
        alpha_threshold: { label: 'Alpha cutoff threshold', type: 'number', value: 0.1, min: 0, max: 1, step: 0.01 },
        alpha_edge_strength: { label: 'Alpha-edge normal strength', type: 'number', value: 2.0, min: 0, max: 8, step: 0.1 },
        preserve_texture_alpha: { label: 'Preserve texture alpha in output', type: 'checkbox', value: false },

        padding: { label: 'Bleed padding in pixels', type: 'number', value: 1, min: 0, max: 32, step: 1 },
        bleed_padding: { label: 'Bleed normal into padding', type: 'checkbox', value: true },
        selected_only: { label: 'Selected cubes only', type: 'checkbox', value: false },
        only_selected_texture: { label: 'Only faces using selected texture', type: 'checkbox', value: false },
        include_untextured: { label: 'Include untextured faces', type: 'checkbox', value: true },
        flip_green: { label: 'Flip green channel', type: 'checkbox', value: false },
        transparent_unused: { label: 'Transparent unused pixels', type: 'checkbox', value: false },
        add_texture: { label: 'Add generated normal as Blockbench texture', type: 'checkbox', value: true },
        save_method: {
          label: 'Save method', type: 'select', value: 'none',
          options: { none: 'Do not save file; add texture only', blob: 'Download PNG using Blob URL', native: 'Desktop folder picker' }
        },
        show_debug: { label: 'Show baked face UV list', type: 'checkbox', value: false }
      },
      onConfirm(form) {
        try {
          let filename = String(form.filename || defaultFilename).trim();
          if (!filename.toLowerCase().endsWith('.png')) filename += '.png';
          const result = bake({
            sizeMode: form.size_mode || 'manual',
            fallbackSize: safeNumber(form.fallback_size, 128),
            radiusModelUnits: safeNumber(form.radius, 1),
            strength: safeNumber(form.strength, 0.8),
            generateSurfaceNormals: !!form.generate_surface_normals,
            surfaceStrength: safeNumber(form.surface_strength, 1.0),
            surfaceSampleRadius: safeNumber(form.surface_sample_radius, 1.0),
            invertSurfaceHeight: !!form.invert_surface_height,
            useAlphaCutout: !!form.use_alpha_cutout,
            alphaGuidedBake: !!form.alpha_guided_bake,
            alphaThreshold: safeNumber(form.alpha_threshold, 0.1),
            alphaEdgeStrength: safeNumber(form.alpha_edge_strength, 2.0),
            preserveTextureAlpha: !!form.preserve_texture_alpha,
            padding: Math.round(safeNumber(form.padding, 1)),
            bleedPadding: !!form.bleed_padding,
            selectedOnly: !!form.selected_only,
            onlySelectedTexture: !!form.only_selected_texture,
            includeUntextured: !!form.include_untextured,
            flipGreen: !!form.flip_green,
            transparentUnused: !!form.transparent_unused
          });

          if (form.add_texture) {
            const ok = addTexture(result.canvas, filename);
            if (!ok) Blockbench.showQuickMessage('Could not add texture, but bake completed.', 4000);
          }
          if (form.save_method === 'blob') saveWithBlobDownload(result.canvas, filename);
          else if (form.save_method === 'native') {
            if (!saveWithNativePicker(result.canvas, filename)) {
              Blockbench.showQuickMessage('Native save unavailable. Trying Blob download.', 4000);
              saveWithBlobDownload(result.canvas, filename);
            }
          }
          Blockbench.showQuickMessage(
            `Baked ${result.usedFaceCount} faces from ${result.usedCubeCount} cubes | UV source ${result.srcW}×${result.srcH} -> output ${result.texW}×${result.texH}`,
            6000
          );
          if (form.show_debug) showDebug(result);
        } catch (e) {
          console.error(e);
          Blockbench.showMessageBox({ title: 'Rounded Box UV Normal Baker', message: e && e.message ? e.message : String(e) });
        }
      }
    });
    dialog.show();
  }

  Plugin.register(PLUGIN_ID, {
    title: 'Rounded Box UV Normal Baker',
    author: 'ChatGPT',
    description: 'Bakes rounded normal maps from multiple Blockbench cubes, layers color-derived surface normals, and can let texture alpha shape the baked normals with a flat normal-color background.',
    icon: 'blur_on',
    version: '4.5.0',
    min_version: '5.0.0',
    variant: 'both',
    onload() {
      bakeAction = new Action('bake_rounded_box_uv_normal_map_v4_5', {
        name: 'Bake Rounded Box UV Normal Map',
        description: 'Bake a smooth normal map into the actual UV layout used by cube faces, including cutout shaping and color-derived surface detail.',
        icon: 'blur_on',
        click: openDialog
      });
      MenuBar.addAction(bakeAction, 'tools');
    },
    onunload() {
      if (bakeAction) bakeAction.delete();
    }
  });
})();
