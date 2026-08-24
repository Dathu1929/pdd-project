package com.smartelectricity.automation.tests;

import io.appium.java_client.AppiumDriver;
import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.options.UiAutomator2Options;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import java.net.MalformedURLException;
import java.net.URL;

public class BaseTest {
    protected AppiumDriver driver;

    @BeforeMethod
    public void setUp() throws MalformedURLException {
        String userDir = System.getProperty("user.dir");
        String appPath = userDir + "/../../android-app/app/build/outputs/apk/debug/app-debug.apk";
        if (!new java.io.File(appPath).exists()) {
            appPath = userDir + "/app/build/outputs/apk/debug/app-debug.apk";
        }

        UiAutomator2Options options = new UiAutomator2Options()
                .setPlatformName("Android")
                .setDeviceName("Android Emulator")
                .setAutomationName("UiAutomator2")
                .setApp(appPath)
                .setNoReset(false);

        driver = new AndroidDriver(new URL("http://127.0.0.1:4723/"), options);
    }

    @AfterMethod
    public void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }
}
