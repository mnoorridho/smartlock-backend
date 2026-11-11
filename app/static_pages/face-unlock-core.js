/* Pure validation/state machine, shared by the camera adapter and automated tests. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SmartlockFaceCore = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MODEL = 'face-api-1.7.15';
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  const CLIENT_VERSION = 'photo-geometry-20261031-v4';
  function quality(face) {
    const b=face.box;
    if(!b || ![b.x,b.y,b.width,b.height].every(finite) || b.width<=0 || b.height<=0) return 'Wajah belum terdeteksi dengan benar';
    if(!finite(face.score) || face.score<.50) return 'Deteksi wajah belum cukup jelas. Hadapkan wajah ke kamera';
    if(face.landmarksVisible!==true) return 'Mata, hidung, dan mulut harus berada di dalam foto';
    if(face.source){
      const src=face.source;
      if(![src.width,src.height,src.faceWidth,src.faceHeight].every(finite)) return 'Ukuran foto tidak valid';
      if(Math.min(src.width,src.height)<360 || Math.max(src.width,src.height)<480) return 'Resolusi kamera terlalu kecil. Gunakan minimal 480 × 360 piksel';
      if(src.faceWidth<100 || src.faceHeight<100) return 'Dekatkan wajah: ukuran wajah dalam foto minimal 100 × 100 piksel';
    }
    // Pixel texture, EAR, and hand-derived yaw/pitch are not calibrated occlusion/pose classifiers.
    // Keep these as diagnostics only; do not reject clear faces because skin has low contrast.
    if(!face.pose || !finite(face.pose.roll)) return 'Posisi wajah belum terbaca';
    if(Math.abs(face.pose.roll)>25) return 'Luruskan kepala sedikit sebelum mengambil foto';
    return null;
  }
  function validDescriptor(d) { return (Array.isArray(d) || ArrayBuffer.isView(d)) && d.length === 128 && Array.from(d).every(v => finite(v) && Math.abs(v) <= 2) && Math.hypot(...d) >= .5 && Math.hypot(...d) <= 2; }
  function distance(a, b) { return Math.sqrt(Array.from(a).reduce((sum, v, i) => sum + (v - b[i]) ** 2, 0)); }
  function compareIdentity(descriptor, profile, threshold = .45) {
    const invalid = {valid:false,matched:false,distance:null,threshold};
    if (!finite(threshold) || threshold < .30 || threshold > .55) return invalid;
    if (!validDescriptor(descriptor) || !profile || profile.model_version !== MODEL || !Array.isArray(profile.descriptors) || ![1,3].includes(profile.descriptors.length) || !profile.descriptors.every(validDescriptor)) return invalid;
    const distances = profile.descriptors.map(ref=>distance(descriptor,ref)).sort((a,b)=>a-b);
    const measured = distances[Math.min(2,distances.length)-1];
    return {valid:true,matched:measured<=threshold,distance:measured,threshold};
  }
  function matchIdentity(descriptor, profile, threshold = .45) { return compareIdentity(descriptor,profile,threshold).matched; }
  return { MODEL, CLIENT_VERSION, quality, validDescriptor, distance, compareIdentity, matchIdentity };
});
