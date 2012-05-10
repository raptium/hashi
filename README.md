# Hashi
Hashi is an HTTP relay server compatible with the Secure Shell chromium extension https://chrome.google.com/webstore/detail/pnhechapfaindjhompbnflcldabbghjo.

## Usages
**WARNING**: Current implementation is very experimental, use at your own risk.
    
To start the server:

    python relay.py
    
The relay server will listen on TCP port 8022 and 8023. You may need to adjust your firewall rules to allow connection.
To connect via the relay server, use `USER@SSH_SERVER[:SSH_PORT]@RELAY_SERVER` as the destination in the secure shell.


## Links
 - http://goo.gl/m6Nj8 chromium-hterm FAQ
 - http://goo.gl/kIj6X source code of the relay client