import os
import base64
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

            # send the results back to the client
            encoded_tiles = []

            for tile in data['tile']:
                # get results from the given URL including tile image
                res = requests.get(tile)
                # encode the tile png into base64
                encoded = base64.b64encode(res.content)
                encoded_tiles.append(encoded)

            # send the results as JSON format back to the client
            self.write({'msg': encoded_tiles})

        def options(self):
            # no body
            self.set_status(204)
            self.finish()


    def main():
        application = tornado.web.Application([
            (r"/tileUrl/", TileUrlHandler)
            ], debug=True)
        port = int(os.environ.get("PORT", 5000))
        application.listen(port)
        tornado.ioloop.IOLoop.current().start()

    if __name__ == "__main__":
            main()
