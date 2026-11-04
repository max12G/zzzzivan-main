(function () {
    const savedTheme = localStorage.getItem('neuroapi-theme');
    const theme = savedTheme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
            button.addEventListener('click', function () {
                const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
                document.documentElement.dataset.theme = nextTheme;
                localStorage.setItem('neuroapi-theme', nextTheme);
                document.querySelectorAll('[data-theme-toggle]').forEach(function (item) {
                    item.setAttribute('aria-label', nextTheme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему');
                    item.querySelector('i').className = nextTheme === 'dark' ? 'ri-sun-line' : 'ri-moon-line';
                });
            });
        });
    });
})();
