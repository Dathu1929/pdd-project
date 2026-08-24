const { Builder, until, By } = require('selenium-webdriver');
const chrome = require('selenium-webdriver/chrome');
const LoginPage = require('../pages/LoginPage');

describe('Smart Electricity Web Portal E2E Tests', () => {
    jest.setTimeout(60000);
    let driver;
    const baseUrl = process.env.BASE_URL || 'http://localhost:8000/';

    beforeAll(async () => {
        let options = new chrome.Options();
        options.addArguments('--headless');
        options.addArguments('--no-sandbox');
        options.addArguments('--disable-dev-shm-usage');

        driver = await new Builder()
            .forBrowser('chrome')
            .setChromeOptions(options)
            .build();
    }, 60000);

    afterAll(async () => {
        if (driver) {
            await driver.quit();
        }
    });

    test('Verify Web Login Workflow', async () => {
        await driver.get(baseUrl);
        const loginPage = new LoginPage(driver);
        await loginPage.login('dattu@gmail.com', 'dattu123');
        
        const appLayout = await driver.wait(until.elementLocated(By.css('#appLayout')), 10000);
        await driver.wait(until.elementIsVisible(appLayout), 10000);
        
        expect(await appLayout.isDisplayed()).toBe(true);
    });
});
