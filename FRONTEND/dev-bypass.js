(function() {
    if (!localStorage.getItem('authToken')) {
        console.log('🔓 개발 모드: 자동 인증');

        const fakePayload = {
            exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 365 // 1년 유효
        };

        const fakeToken = 
            "header." + 
            btoa(JSON.stringify(fakePayload)) + 
            ".signature";

        localStorage.setItem('authToken', fakeToken);
        localStorage.setItem('user', JSON.stringify({
            id: 'dev-user',
            name: '개발자',
            email: 'dev@ftoguard.com'
        }));
    }
})();
