from pyhafas import HafasClient
from pyhafas.profile import OebbProfile
import pyhafas.profile; print(dir(pyhafas.profile))

client = HafasClient(OebbProfile())

for name in ["Wien Hernals", "Wien Heiligenstadt", "Krems an der Donau"]:
    print(f"\n--- {name} ---")
    for loc in client.locations(name)[:3]:
        print(f"  id={loc.id}  name={loc.name}  lat={loc.latitude}  lon={loc.longitude}")