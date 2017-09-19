from bs4 import BeautifulSoup
import json
import requests
from datetime import datetime, date
from time import sleep
from getpass import getpass


class Register(object):
    """
    Class that will Register a student for classes on Banner Self Service website.
    """

    page_urls = { # urls for different pages on the site (last part of URL address)
        'home' : '/twbkwbis.P_WWWLogin',
        'login' : '/twbkwbis.P_ValLogin',
        'list_term' : '/bwskflib.P_SelDefTerm',
        'store_term' : '/bwcklibs.P_StoreTerm',
        'register' : '/bwckcoms.P_Regs',
        'add_drop' : '/bwskfreg.P_AltPin',
    }

    def __init__(self, url, username, password=None):
        # capture the password if it wasn't given
        if (password == None):
            password = getpass("Enter the password for %s:" % (username))
        
        self.base_url = url # base URL, as in https://bannerweb.wpi.edu
        self.session = requests.Session() # start up a session to load the page

        # determine the part of the URL that sits between the base and page, as in /pls/prod
        self.middle_url = None # URL between base and page
        for attempt in ['/pls/owa_prod', '/pls/prod']: # try both to see which is valid
            response = self.session.send(self.prepped_request(self.page_urls['home'], "GET", middle_url=attempt)) # load the login page

            if (response.status_code == requests.codes.ok): # found the correct middle url
                self.middle_url = attempt
                break

        # make sure a middle url was found
        if (self.middle_url == None):
            raise Exception("Couldn't determine the full URL!");

        # log the user into a session
        response = self.session.send(self.prepped_request(self.page_urls['login'], "POST", data={'sid':username, 'PIN':password}))
        
        # make sure the user is authenticated
        if (response.cookies.get('SESSID') == None): # not authenticated
            raise Exception("Invalid login credentials!");
        else:
            # find out how long until the cookie expires
            pass

        # load a list of available terms to make sure the user entered a correct one, or prompt to enter one
        # load the list_term page to see available terms
        page = self.session.get(self.base_url + self.middle_url + self.page_urls['list_term'], headers={'referer':self.base_url})
        soup = BeautifulSoup(page.text, 'html5lib') # need to user html5lib because default parser can't comprehend option blocks
        
        # capture the exact time offset of the server
        self.offset = datetime.strptime(response.headers['Date'], '%a, %d %b %Y %H:%M:%S %Z') - datetime.utcnow()

        self.cache = None

    def register(self, classes=[], time=None, term=None):
        """
        Register for a list of classes (by CRN).
        classes: list of crns to register as strings
        time: time to register, in the form hh:mm, 24 hour format
        """
        
        if (time):
            time_to_register = datetime.now() # time to register, assuming it's today
            time_to_register = time_to_register.replace(hour=int(time.split(":")[0]), minute=int(time.split(":")[1]), second=0, microsecond=0) # change time to register to desired
            time_to_wait = time_to_register - datetime.now() - self.offset
            # if there is time to wait before registration then wait
            if (time_to_wait.total_seconds() > 0.):
                print("Ok, going to wait " + str(time_to_wait.total_seconds()) + " seconds, then register!")

                sleep(time_to_wait.total_seconds())


        if (not self.cache):
            prepped = self.prepped_request(self.page_urls['add_drop'], "POST", { 'term_in' : '201609' }) # request to view the add/drop page with term id
            response = self.session.send(prepped) # send the request for the add/drop page
            form = BeautifulSoup(response.text, 'html5lib').find('form', {'action':self.middle_url + self.page_urls['register']}) # soup for the add/drop form
            self.cache = form
        else:
            form = self.cache

        # extract data from the add/drop form to send to the next request
        # this is done in the way that it is to preserve the order of the input fields on the page. if sent out of order, banner will not accept them
        data = [] # to hold the data for the register request
        for input in form.find_all('input'):
            # don't include any inputs that don't have a name or that are a submit button
            if (input.get('name') and not input.get('type') == 'submit' and not input.get('name') == 'term_in'):
                data.append(input.get('name') + '=' + (input.get('value') or ''))
                
        # add the submit changes button value
        data.append('REG_BTN=Submit+Changes')

        data.append('term_in=' + term)

        # convert the data to a query string (?key=value&key=value)
        data = '&'.join(data)

        # add the classes crns to the request
        for crn in classes:
            data = data.replace('CRN_IN=&', 'CRN_IN=' + crn + '&', 1) # add the CRNs to the query string by replacing empty CRN_IN values
            
        # make the register request
        prepped = self.prepped_request(self.page_urls['register'], "POST", data) # prepped request to register

        response = self.session.send(prepped) # send the register request
        error_table = BeautifulSoup(response.text, 'html.parser').find('table', {'summary': "This layout table is used to present Registration Errors."})
        failed_crns = [] # the crns that couldn't be registered

        if (error_table): # something failed
            message = "Failures:\n"
            for row in error_table.find_all('tr')[1:]:
                cells = row.find_all('td')
                failed_crns.append(cells[1].text)
                message += 'CRN:' + cells[1].text + ' | ' + cells[0].text + ' | ' + cells[2].text + ' ' + cells[3].text + ' ' + cells[8].text + ' ' + cells[3].text + '\n'
        else:
            message = "Success!"

        print(message)

        return failed_crns


    def prepped_request(self, page_url, method, data={}, middle_url=None):
        """
        Create a prepared request that can be used as a base for more complicated requests.
        Parameters of the returned prepared request will be ready to be send(), but parameters
            of the request can be updated before the request is actually sent.
        This does NOT send a request; it only builds a request to be made later using send().

        page_url: the url of the specific page to be requested
        method: the request method that the request should be prepared for, ie "POST" or "GET"
        data: a dictionary of data to be put in the prepped request
        middle_url: should be good how it is (uses self.middle_url), but the url that connects the base_url to the page_url
        """
        if (middle_url == None):
            middle_url = self.middle_url

        # prevent too many requests too quickly
        sleep(0.5)

        # prepare the request with the correct url and headers
        prepped = requests.Request(method, self.base_url + middle_url + page_url, headers={'referer':self.base_url}, data=data);
        print("Prepped Request:" + self.base_url + middle_url + page_url)
        return self.session.prepare_request(prepped) # return the prepped request

while (True):
    crn = input("Enter a CRN to register for:")
    reg.register([crn], term="201609")

def client():
    """
    Interactive client for the Register class
    """
    schedules = [ # possible schedules
        [{ "12345": "EN1251", "10234" : "CS2303" }, { "12645" : "EN1251" , "19734" : "CS4303" }],
        [{ "12645": "EN1251", "10254" : "CS2303" }, { "12345" : "EN2251" , "19234" : "CS4303" }],
    ]
    terms = ["201701", "201702"] # the terms to register for, with postions corresponding to order in schedules
    current_registration = schedules[0] # the courses that are currently enrolled for
    registration_time = "21:00"
    failed_crns = []

    print("Getting ready to register...")
    reg = Register("https://bannerweb.wpi.edu", "username", "password")
    print("Logged in successfully! Now going to register for your first schedule")
    
    # register for the first schedule
    for term_index in range(len(terms)): # for each term
        print("Processing term " + terms[term_index] + "...")

        failed_crns.append(reg.register(schedules[0][term_index].keys(), registration_time, terms[term_index]))

        # remove the failed CRNs from the current registration
        for crn in failed_crns[term_index]: # go through the failed crns
            del current_registration[term_index][crn]

    # now lets try to finish the registration process if there were any errors
    done = False if len(failed_crns) != 0 else True # indicates whether all classes have been registered for
    while(not done): # while there isn't a complete schedule choosen
        for term_index in range(len(terms)):
            # print available schedules and what it would would need to change for it
            print("Available schedules for term " + terms[term_index] + ":")
            for schedule_index in len(schedules): # for each possible schedule
                difference = compare(current_registration[term_index], schedules[schedule_index][term_index])
                print("# " + schedule_index + ": DROP:" + str(difference["drop"]) + " | ADD:" + str(difference["add"]))
            input = input("Enter a schedule number or N to cancel:") # ask the user to choose a schedule
            if (input != 'n' and input != 'N'): # user wants to register
                pass

def compare(current_crns, desired_crns):
    """
    Compares the currently registered crns to a desired list of crns, and returns a list
        of crns crns that would have to be dropped and a list that would have to be added.
    """
    difference = { "add" : [] , "drop" : [] } # differences between current and desired

    # determine what classes would need to be added
    for crn in current_crns:
        if (not crn in desired_crns): # need to add this class
            differences["add"].append(crn)

    # determine what classes would need to be dropped
    for crn in desired_crns:
        if (not crn in current_crns): # need to drop this class
            differences["drop"].append(crn)

    return difference

client()