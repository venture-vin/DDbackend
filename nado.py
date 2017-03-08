import os
import requests
import tornado.ioloop
import tornado.web


class TileUrlHandler(tornado.web.RequestHandler):
    # Headers set to avoid CORS issue of getting info from other URLs

    def set_default_headers(self):
        # allow cross-origin requests to be made from your app on DroneDeploy to your web server
        self.set_header("Access-Control-Allow-Origin", "https://www.dronedeploy.com")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        # add more allowed methods when adding more handlers (POST, PUT, etc.)
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def post(self):
        json_data = tornado.escape.json_decode(self.request.body)

        self.write({'response': json_data})

    def options(self):
        # no body
        self.set_status(204)
        self.finish()


def main():
    application = tornado.web.Application([
        (r"/", TileUrlHandler)
    ], debug=True)
    port = int(os.environ.get("PORT", 5000))
    application.listen(port)
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
        main()
