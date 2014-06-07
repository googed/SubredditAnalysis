from collections import Counter
from datetime import datetime
import logging
import operator
from sys import exit, stderr
from time import sleep
import praw
from requests import HTTPError


class SubredditAnalysis(object):


    def __init__(self):
        """
        Initialize the class with some basic attributes.
        """

        # maximum threads to crawl. Reddit doesn't
        # like it when you go over 1000
        self.scrapeLimit = 1000

        # post drilldown to this subreddit
        self.post_to = "SubredditAnalysis"

        self.useragent = "Reddit Analysis Bot by /u/SirNeon"

        # keep count of how many attempts have been made
        # to get a list of users for the target subreddit
        self.userRetry = 0

        # keep count of how many attempts have been made
        # to get a list of subreddits for the target subreddit
        self.subRetry = 0

        # keep count of how many attempts have been made
        # to submit a post to Reddit
        self.submitRetry = 0

        # optional logging
        self.infoLogging = True
        self.postLogging = True

        # I've banned defaults and former defaults since
        # there's bound to be overlap with those due to
        # how Reddit autosubscribes users to them
        self.banList = [
            "AdviceAnimals", "announcements", "Art", "atheism",
            "AskReddit", "askscience", "aww", "bestof",
            "blog", "books", "creepy", "dataisbeautiful",
            "DIY", "Documentaries", "EarthPorn",
            "explainlikeimfive", "Fitness", "food", "funny",
            "Futurology", "gadgets", "gaming", "GetMotivated",
            "gifs", "history", "IAmA", "InternetIsBeautiful",
            "Jokes", "LifeProTips", "listentothis",
            "mildlyinteresting", "movies", "Music", "news",
            "nosleep", "nottheonion", "OldSchoolCool",
            "personalfinance", "philosophy",
            "photoshopbattles", "pics", "politics", "science",
            "Showerthoughts", "space", "sports", "technology",
            "television", "tifu", "todayilearned",
            "TwoXChromosomes", "UpliftingNews", "videos",
            "worldnews", "WritingPrompts", "WTF"
        ]


    def login(self, username, password):
        """
        This function logs the bot into its Reddit account.
        It takes 2 arguments: the username and the password.
        """

        self.client = praw.Reddit(user_agent=self.useragent)
        print "Logging in..."

        self.client.login(username, password)
        print "Login successful."


    def get_users(self, subreddit):
        """
        This function creates a list of users that posted in
        the subreddit which is being scanned. The data from these
        users is then collected to determine where else they post.
        It takes 1 argument, which is the subreddit to be scanned.
        It returns a list of users.
        """

        print "Getting users for /r/%s..." % subreddit

        # get threads from the hot list
        submissions = self.client.get_subreddit(subreddit).get_hot(limit=self.scrapeLimit)

        # userbase in the selected subreddit to be scanned
        self.userList = []

        # get the thread creator and if he's not
        # in the userList then add him there
        for i, submission in enumerate(submissions):
            try:
                submitter = str(submission.author)

            except AttributeError:
                continue

            # make sure that users don't get added multiple times
            if submitter not in self.userList:
                self.userList.append(submitter)
                print "%d users found up to thread (%d / %d)." % (len(self.userList), i + 1, self.scrapeLimit)


            # load more comments
            submission.replace_more_comments(limit=None, threshold=0)

            # get the comment authors and append
            # them to userList for scanning
            for comment in praw.helpers.flatten_tree(submission.comments):
                try:
                    commenter = str(comment.author)

                except AttributeError:
                    continue

                if commenter not in self.userList:
                    self.userList.append(commenter)
                    print "%d users found up to thread (%d / %d)." % (len(self.userList), i + 1, self.scrapeLimit)

        return self.userList


    def get_subs(self, userList):
        """
        This function uses the list collected by get_users()
        in order to find the crossover subreddits. It takes 1
        argument which is a list of users to scan through.
        It then stores the results in a list which will be
        put into tuples and then sorted. It returns a list of
        subreddits.
        """

        print "Scanning for overlapping subreddits..."

        # list of overlapping subreddits
        subredditList = []

        # keeps count on overlapping users
        self.counter = Counter()

        # iterate through the list of users in order
        # to get their comments for crossreferencing
        for i, user in enumerate(userList):
            try:
                comments = self.client.get_redditor(user).get_comments('all')

            # handle shadowbanned/deleted accounts
            except HTTPError:
                continue

            # keeps track of user subs to prevent multiple
            # posts from being tallied
            self.userDone = []

            # keeps track of how many users are remaining
            usersLeft = len(userList) - i - 1

            print "(%d / %d) users remaining." % (usersLeft, len(userList))

            for comment in comments:
                try:
                    csubreddit = str(comment.subreddit)

                except AttributeError:
                    continue

                if csubreddit not in self.userDone:
                    # keep tabs on how many
                    # users post to a subreddit
                    self.counter[csubreddit] += 1
                    self.userDone.append(csubreddit)

                # add the ones that aren't kept in the list
                # to the list of subreddits
                if((csubreddit not in subredditList) & (csubreddit not in self.banList)):
                    subredditList.append(csubreddit)

        return subredditList


    def create_tuples(self, subreddit, subredditList):
        """
        This function takes 2 arguments, the first which
        is the subreddit that is being targeted for the drilldown.
        The second is the list of subreddits which will be put
        into tuples for storage. It returns a list of tuples that
        contains the subreddit, the overlapping users, and their
        net karma.
        """

        print "Creating tuples..."

        # stores the tuples to be used for printing data
        self.subredditTuple = []

        # create a bunch of tuples and adds them to a list
        # to neatly store the collected data for future sorting
        for item in subredditList:
            # avoids including posts made
            # in the selected subreddit
            # also exclude crossovers with less than 10 posters
            self.intCounter = int(self.counter[item])
            if((item.lower() != subreddit.lower()) & (self.intCounter >= 10)):
                self.subredditTuple.append((item, self.intCounter))

        # sorts biggest to smallest by the 2nd tuple value
        # which is the post tally
        self.subredditTuple.sort(key=operator.itemgetter(1), reverse=True)

        return self.subredditTuple


    def format_post(self, subreddit, subredditTuple, userList):
        """
        This function formats the data in order to submit it to
        Reddit. It takes 3 arguments. The first is the subreddit
        that is being targeted for the drilldown. The second is
        the list of tuples for printing data. The last is the
        list of users in order to print the total amount of users
        discovered by the bot. It returns the formatted string.
        """

        print "Formatting post..."

        # make a table
        self.bodyStart = "## /r/%s Drilldown\n\n" % subreddit
        self.bodyStart += "Of %d Users Found:\n\n" % len(userList)
        self.bodyStart += "| Subreddit | Overlapping users |\n"
        self.bodyStart += "|:------|------:|\n"

        self.bodyContent = ""

        # fill in the table
        for i in range(0, len(subredditTuple)):
            sub = "".join(subredditTuple[i][0])
            overlap = "".join(str(subredditTuple[i][1]))
            self.bodyContent += "|/r/%s|%s|\n" % (sub, overlap)

            if len(self.bodyStart + self.bodyContent) >= 9900:
                # so the table doesn't get too big to post
                break

        text = self.bodyStart + self.bodyContent

        return text


    def submit_post(self, subreddit, text):
        """
        This function submits the results to Reddit. It takes
        two arguments. The first is the subreddit that was
        targeted for the drilldown. The second is the text for
        the submission thread.
        """

        print "Submitting post..."

        # post to this subreddit
        self.mySubreddit = self.client.get_subreddit(self.post_to)

        # thread title
        title = "/r/%s Drilldown %s" % (subreddit, datetime.now().strftime("%B %Y"))

        # finally submit it
        return self.mySubreddit.submit(title, text)
    

    def log_info(self, info):
        """
        This is for logging raw data in case you want to.
        """

        if(self.infoLogging):
            self.logDate = str(datetime.now().strftime("%Y-%m-%d"))
            self.logName = "SubredditAnalysis_%s.txt" % (self.logDate)
            self.logFile = open(self.logName, 'a')

            self.logFile.write(str(info))

            self.logFile.close()


    def log_post(self, subreddit, post):
        """
        In the event that the bot can not submit a post to
        Reddit, this function will write that post to a text file
        so that your time isn't wasted. It takes 2 arguments: the
        drilldown subreddit and the post.
        """

        if(self.postLogging):
            self.logName = "%s_results.txt" % subreddit
            self.postFile = open(self.logName, 'a')

            self.postFile.write(str(post))

            self.postFile.close()


if __name__ == "__main__":
    myBot = SubredditAnalysis()

    # set these to False if you don't want logs
    myBot.infoLogging = True
    errorLogging = True
    myBot.postLogging = True

    if(errorLogging):
        logging.basicConfig(
            filename="SubredditAnalysis_logerr.log", 
            filemode='a', format="%(asctime)s\nIn "
            "%(filename)s (%(funcName)s:%(lineno)s): "
            "%(message)s", datefmt="%Y-%m-%d %H:%M:%S", 
            level=logging.DEBUG, stream=stderr
        )

    # login credentials
    username = ""
    password = ""

    print "Welcome to Reddit Analysis Bot."

    print "Type \"quit\", \".quit\", or \'q\' to exit the program."

    try:
        myBot.login(username, password)

    except (praw.errors.InvalidUser, praw.errors.InvalidUserPass, HTTPError) as e:
            print e
            logging.debug(str(error) + "\n\n")
            exit(1)

    while True:
        # list of subreddits you want to analyze
        drilldownList = raw_input("Enter the subreddits you wish to target.~/> ").split()

        # iterate through the drilldownList to get data
        for subreddit in drilldownList:

            if(subreddit in ['quit', '.quit', 'q']):
                print "Quitting..."
                exit(0)

            else:
                # get the list of users
                try:
                    userList = myBot.get_users(subreddit)
                    myBot.userRetry = 0

                except HTTPError, e:
                    print e
                    logging.debug(str(error) + "\n\n")

                    # try this 3 times
                    while myBot.userRetry <= 3:
                        # wait 5 minutes and try again
                        # maybe Reddit broke and just needs some time
                        print "Waiting 5 minutes to try again..."
                        sleep(300)

                        try:
                            userList = myBot.get_users(subreddit)
                            break

                        except Exception, e:
                            print e
                            logging.debug(str(error) + "\n\n")
                            myBot.userRetry += 1
                    
                    if myBot.userRetry > 3:
                        print "Failed to get users."
                        exit(1)

                except Exception, e:
                    print e
                    logging.debug(str(error) + "\n\n")
                    exit(1)

                for user in userList:
                    myBot.log_info(user + ',')

                myBot.log_info("\n\n")


                try:
                    # get the list of subreddits
                    subredditList = myBot.get_subs(userList)
                    myBot.subRetry = 0

                except HTTPError, e:
                    print e
                    logging.debug(str(error) + "\n\n")

                    while myBot.subRetry <= 3:

                        # wait 5 minutes and try again
                        # maybe Reddit broke and just needs some time
                        print "Waiting 5 minutes to try again..."
                        sleep(300)

                        try:
                            subredditList = myBot.get_subs(subreddit)
                            break

                        except Exception, e:
                            print e
                            logging.debug(str(error) + "\n\n")
                            myBot.subRetry += 1
                    
                    if myBot.subRetry > 3:
                        print "Failed to get overlapping subreddits."
                        exit(1)

                except Exception, e:
                    print e
                    logging.debug(str(error) + "\n\n")
                    exit(1)

                for sub in subredditList:
                    myBot.log_info(sub + ',')

                myBot.log_info("\n\n")


                try:
                    # get the list of tuples
                    subredditTuple = myBot.create_tuples(subreddit, subredditList)

                    for item in subredditTuple:
                        myBot.log_info(item)
                        myBot.log_info(',')

                    myBot.log_info("\n\n")

                    # format the data for Reddit
                    text = myBot.format_post(subreddit, subredditTuple, userList)

                except Exception, e:
                    print e
                    logging.debug(str(error) + "\n\n")
                    exit(1)

                try:
                    # submit the post for Reddit
                    post = myBot.submit_post(subreddit, text)
                    myBot.submitRetry = 0

                    # this requires mod privileges
                    print "Setting post's flair..."
                    myBot.client.set_flair(myBot.post_to, post, flair_text=subreddit)

                except HTTPError, e:
                    print e
                    logging.debug(str(error) + "\n\n")

                    while myBot.submitRetry <= 3:

                        print "Waiting 5 minutes to try again..."
                        sleep(300)

                        try:
                            post = myBot.submit_post(subreddit, text)
                            
                            print "Setting post's flair..."
                            myBot.client.set_flair(myBot.post_to, post, flair_text=subreddit)
                            break

                        except Exception, e:
                            print e
                            logging.debug(str(error) + "\n\n")
                            myBot.submitRetry += 1

                    if myBot.submitRetry > 3:
                        print "Failed to submit post."
                        myBot.log_post(subreddit, text)
                        exit(1)
                
                except Exception, e:
                    print e
                    logging.debug(str(error) + "\n\n")
                    myBot.log_post(subreddit, text)
                    exit(1)
