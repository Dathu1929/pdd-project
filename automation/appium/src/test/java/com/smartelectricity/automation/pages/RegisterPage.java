package com.smartelectricity.automation.pages;

import io.appium.java_client.AppiumDriver;
import io.appium.java_client.pagefactory.AndroidFindBy;
import io.appium.java_client.pagefactory.AppiumFieldDecorator;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.PageFactory;

public class RegisterPage extends BasePage {

    @AndroidFindBy(id = "com.smartelectricity.app:id/et_register_name")
    private WebElement nameField;

    @AndroidFindBy(id = "com.smartelectricity.app:id/et_register_email")
    private WebElement emailField;

    @AndroidFindBy(id = "com.smartelectricity.app:id/et_register_password")
    private WebElement passwordField;

    @AndroidFindBy(id = "com.smartelectricity.app:id/et_register_phone")
    private WebElement phoneField;

    @AndroidFindBy(id = "com.smartelectricity.app:id/act_board")
    private WebElement boardDropdown;

    @AndroidFindBy(id = "com.smartelectricity.app:id/et_captcha_input")
    private WebElement captchaField;

    @AndroidFindBy(id = "com.smartelectricity.app:id/tv_captcha_val")
    private WebElement captchaVal;

    @AndroidFindBy(id = "com.smartelectricity.app:id/cb_agree")
    private WebElement agreeCheckbox;

    @AndroidFindBy(id = "com.smartelectricity.app:id/btn_register")
    private WebElement registerButton;

    @AndroidFindBy(id = "com.smartelectricity.app:id/tv_login_back")
    private WebElement loginLink;

    public RegisterPage(AppiumDriver driver) {
        super(driver);
        PageFactory.initElements(new AppiumFieldDecorator(driver), this);
    }

    public void register(String name, String email, String password, String phone, String board) {
        type(nameField, name);
        type(phoneField, phone);
        type(emailField, email);
        type(passwordField, password);
        
        click(boardDropdown);
        // Captcha verification bypass helper
        String currentCaptcha = captchaVal.getText().replace(" ", "");
        type(captchaField, currentCaptcha);

        if (!agreeCheckbox.isSelected()) {
            click(agreeCheckbox);
        }
        click(registerButton);
    }
}
