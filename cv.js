// JavaScript for /cv/index.html modularized
mermaid.initialize({ startOnLoad: true });
// Collapsible Sections
document.querySelectorAll('h2').forEach(header => {
  header.addEventListener('click', () => {
    const content = header.nextElementSibling;
    content.classList.toggle('active');
    header.classList.toggle('active');
  });
});
// Verbose Mode Toggle
const verboseToggle = document.getElementById('verboseToggle');
if (verboseToggle) {
  verboseToggle.addEventListener('click', () => {
    const isVerbose = verboseToggle.textContent === 'Verbose Mode: Off';
    document.querySelectorAll('.concise').forEach(el => el.classList.toggle('active', !isVerbose));
    document.querySelectorAll('.verbose').forEach(el => el.classList.toggle('active', isVerbose));
    document.querySelectorAll('.mermaid-diagram').forEach(el => el.style.display = isVerbose ? 'block' : 'none');
    verboseToggle.textContent = isVerbose ? 'Verbose Mode: On' : 'Verbose Mode: Off';
  });
}
// Theme Switcher
const themeSelect = document.getElementById('themeSelect');
if (themeSelect) {
  themeSelect.addEventListener('change', (e) => {
    document.body.className = e.target.value;
  });
}
// Progress Bar and Back to Top
window.addEventListener('scroll', () => {
  const scrollTop = window.scrollY;
  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  const scrollPercent = (scrollTop / docHeight) * 100;
  document.querySelector('.progress-bar').style.width = scrollPercent + '%';
  document.getElementById('backToTop').style.display = scrollTop > 100 ? 'block' : 'none';
});
const backToTop = document.getElementById('backToTop');
if (backToTop) {
  backToTop.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}
