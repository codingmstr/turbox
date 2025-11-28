from .base import Base

class Bigo(Base):

    def credentials ( self, phone: str, country: str, password: str ):

        self.phone      = phone
        self.country    = country
        self.password   = password
        self.timeout    = 10000
        self.transition = 20
        self.token_key  = "_%bigolive-web-token%_"
        self.url        = "https://www.bigo.tv/static-fed/reseller/index.html?source=quickly_pay#/login?redirect=agentIndex"
        self.iframe     = "https://www.bigo.tv/ssr/login-iframe?source=reseller"

        return self

    def workflow ( self ):

        self.load_frame().wait(5)

        self.click('.right-top-change', self.frame)

        self.click('.CountrySelect-Component .input-container input.current_selected', self.frame)

        self.get('.country_list_box', self.frame)

        self.select('.country_list li', '.country_name', self.frame, self.country)

        self.fill('.phone-number-box input', self.frame, self.phone)

        self.fill('.password-tab input[type="password"]', self.frame, self.password)

        self.check('.enter_policy_agree_checkbox', self.frame)

        self.move('#captcha-box-login-bigo-captcha-element-bigo-captcha-sliderele', self.frame, 260)

        self.wait(2).click('button.btn-sumbit', self.frame)

        self.token = self.wait(5).local_storage(self.token_key)
