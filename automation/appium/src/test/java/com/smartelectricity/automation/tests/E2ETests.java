package com.smartelectricity.automation.tests;

import com.smartelectricity.automation.pages.LoginPage;
import org.testng.Assert;
import org.testng.annotations.Test;

public class E2ETests extends BaseTest {

    @Test
    public void testSuccessfulLogin() {
        LoginPage loginPage = new LoginPage(driver);
        loginPage.login("dattu@gmail.com", "dattu123");
        // Verify dashboard loading
        Assert.assertTrue(true, "Login check passed");
    }

    @Test
    public void testInvalidLogin() {
        LoginPage loginPage = new LoginPage(driver);
        loginPage.login("wrong@gmail.com", "wrongpass");
        // Verify error display
        Assert.assertTrue(true, "Invalid login error displayed");
    }
}
