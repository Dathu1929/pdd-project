class LoginPage {
    constructor(driver) {
        this.driver = driver;
        this.emailInput = '#loginEmail';
        this.passwordInput = '#loginPassword';
        this.loginBtn = '#loginForm button[type="submit"]';
    }

    async login(email, password) {
        await this.driver.findElement({ css: this.emailInput }).sendKeys(email);
        await this.driver.findElement({ css: this.passwordInput }).sendKeys(password);
        await this.driver.findElement({ css: this.loginBtn }).click();
    }
}

module.exports = LoginPage;
