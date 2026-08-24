package com.smartelectricity.automation.pages;

import io.appium.java_client.AppiumDriver;
import io.appium.java_client.pagefactory.AndroidFindBy;
import io.appium.java_client.pagefactory.AppiumFieldDecorator;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.PageFactory;

public class LoginPage extends BasePage {

    @AndroidFindBy(id = "com.smartelectricity.app:id/etEmail")
    private WebElement emailField;

    @AndroidFindBy(id = "com.smartelectricity.app:id/etPassword")
    private WebElement passwordField;

    @AndroidFindBy(id = "com.smartelectricity.app:id/btnLogin")
    private WebElement loginButton;

    @AndroidFindBy(id = "com.smartelectricity.app:id/tvRegister")
    private WebElement registerLink;

    public LoginPage(AppiumDriver driver) {
        super(driver);
        PageFactory.initElements(new AppiumFieldDecorator(driver), this);
    }

    public void login(String email, String password) {
        type(emailField, email);
        type(passwordField, password);
        click(loginButton);
    }

    public void navigateToRegister() {
        click(registerLink);
    }
}
