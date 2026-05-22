document.querySelectorAll('.form-control').forEach(input => {
  input.addEventListener('focus', function () {
    this.parentElement.style.transform = 'translateY(-2px)';
  });
  input.addEventListener('blur', function () {
    this.parentElement.style.transform = 'translateY(0)';
  });
});

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.alert-dismissible').forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.6s ease';
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 400);
    }, 1250);
  });
});
