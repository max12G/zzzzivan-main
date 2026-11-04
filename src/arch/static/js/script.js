$(document).ready(function() {
    // Обработчик формы регистрации
    $('#register-form').on('submit', function(e) {
        e.preventDefault();
        let valid = true;
        $('.error-msg').hide();

        const fullname = $('#fullname').val().trim();
        const email = $('#email').val().trim();
        const password = $('#password').val();
        const confirm_password = $('#confirm_password').val();

        // Валидация
        if (fullname === '') {
            showError('fullname', 'Введите ваше имя');
            valid = false;
        }

        if (!email.includes('@') || email.length < 5) {
            showError('email', 'Введите корректный Email');
            valid = false;
        }

        if (password.length < 6) {
            showError('password', 'Пароль должен быть длиннее 6 символов');
            valid = false;
        }

        if (password !== confirm_password) {
            showError('confirm_password', 'Пароли не совпадают');
            valid = false;
        }

        // Если всё ок — отправляем AJAX
        if (valid) {
            $.ajax({
                url: '/user_register',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    name: fullname,
                    email: email,
                    password: password
                }),
                success: function(response) {
                    alert('Регистрация прошла успешно! Теперь вы можете войти.');
                    window.location.href = '/login';
                },
                error: function() {
                    alert('Ошибка на сервере. Попробуйте позже.');
                }
            });
        }
    });

    // Обработчик формы входа
    $('#login-form').on('submit', function(e) {
        e.preventDefault();
        let valid = true;
        $('.error-msg').hide();

        const username = $('#username').val().trim();
        const password = $('#password').val();

        if (username === '') {
            showError('username', 'Введите логин или Email');
            valid = false;
        }
        if (password === '') {
            showError('password', 'Введите пароль');
            valid = false;
        }

        if (valid) {
            $.ajax({
                url: '/user_login',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    username: username,
                    password: password
                }),
                success: function(response) {
                    if (response.status === 'ok') {
                        // Перенаправляем на страницу, которую прислал бэкенд
                        window.location.href = response.redirect;
                    }
                },
                error: function(xhr) {
                    const err = xhr.responseJSON;
                    if (err && err.message) {
                        alert(err.message);
                    } else {
                        alert('Ошибка входа');
                    }
                }
            });
        }
    });
    function showError(inputId, message) {
        $(`#${inputId}`).css('border-color', '#dc3545');
        $(`#${input_id}-error`).text(message).show();
    }
});
// Мобильное меню (бургер)
$('#mobileMenuBtn').on('click', function() {
    $('#topbarNav').toggleClass('active');
});

// Закрытие мобильного меню при клике на ссылку (опционально, но удобно)
$('#topbarNav li a').on('click', function() {
    if ($(window).width() < 768) {
        $('#topbarNav').removeClass('active');
    }
});
