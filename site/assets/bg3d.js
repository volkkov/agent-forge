/* Agent Forge — 3D background
   A sphere of glowing nodes connected by faint lines, sitting behind
   the page content as an ambient backdrop. Each node loosely represents
   a repo in the directory; colors echo the health palette (teal/amber/coral).
   Auto-rotates slowly; responds to drag and scroll for a sense of depth.
   Pointer events pass through to the page (canvas is not interactive by
   itself) so it never blocks clicks on real UI underneath it.
*/

(function () {
  function init() {
    var canvas = document.getElementById("bg3d-canvas");
    if (!canvas || typeof THREE === "undefined") return;

    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(55, 1, 0.1, 100);
    camera.position.set(0, 0, 15);

    function resize() {
      var w = window.innerWidth;
      var h = window.innerHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    resize();
    window.addEventListener("resize", resize);

    var TEAL = 0x5eead4;
    var AMBER = 0xf0b25e;
    var CORAL = 0xfb7185;
    var colorCycle = [TEAL, TEAL, TEAL, AMBER, TEAL, TEAL, CORAL, TEAL, TEAL, AMBER];

    var group = new THREE.Group();
    scene.add(group);

    var nodePositions = [];
    var count = 30;
    for (var i = 0; i < count; i++) {
      var phi = Math.acos(-1 + (2 * i) / count);
      var theta = Math.sqrt(count * Math.PI) * phi;
      var r = 10;
      var x = r * Math.cos(theta) * Math.sin(phi);
      var y = r * Math.sin(theta) * Math.sin(phi);
      var z = r * Math.cos(phi);
      nodePositions.push(new THREE.Vector3(x, y, z));

      var size = 0.035 + Math.random() * 0.035;
      var col = colorCycle[i % colorCycle.length];

      var geo = new THREE.SphereGeometry(size, 10, 10);
      var mat = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.9 });
      var sphere = new THREE.Mesh(geo, mat);
      sphere.position.copy(nodePositions[i]);
      group.add(sphere);

      var glowGeo = new THREE.SphereGeometry(size * 3, 8, 8);
      var glowMat = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.15 });
      var glow = new THREE.Mesh(glowGeo, glowMat);
      glow.position.copy(nodePositions[i]);
      group.add(glow);
    }

    var lineMat = new THREE.LineBasicMaterial({ color: 0x5eead4, transparent: true, opacity: 0.4 });
    for (var a = 0; a < count; a++) {
      for (var b = a + 1; b < count; b++) {
        if (nodePositions[a].distanceTo(nodePositions[b]) < 5 && Math.random() > 0.7) {
          var lineGeo = new THREE.BufferGeometry().setFromPoints([nodePositions[a], nodePositions[b]]);
          group.add(new THREE.Line(lineGeo, lineMat));
        }
      }
    }

    // gentle parallax from mouse position, no drag/scroll capture —
    // the canvas must stay click-through for the real page underneath
    var targetRotX = 0.2;
    var targetRotY = 0;
    var currentRotX = 0.2;
    var currentRotY = 0;

    window.addEventListener("mousemove", function (e) {
      var nx = e.clientX / window.innerWidth - 0.5;
      var ny = e.clientY / window.innerHeight - 0.5;
      targetRotY = nx * 0.4;
      targetRotX = 0.2 + ny * 0.25;
    });

    var autoRotate = 0;
    var prefersReducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function animate() {
      requestAnimationFrame(animate);
      if (!prefersReducedMotion) {
        autoRotate += 0.0009;
      }
      currentRotX += (targetRotX - currentRotX) * 0.02;
      currentRotY += (targetRotY - currentRotY) * 0.02;
      group.rotation.x = currentRotX;
      group.rotation.y = currentRotY + autoRotate;
      renderer.render(scene, camera);
    }
    animate();
  }

  if (document.readyState === "complete" || document.readyState === "interactive") {
    setTimeout(init, 0);
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
