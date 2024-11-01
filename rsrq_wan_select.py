from csclient import EventingCSClient
from collections import Counter
import time

cp = EventingCSClient('rsrq_wan_select')

def check_uptime():
    uptime_req = 120

    uptime  = int(cp.get('status/system/uptime'))
    cp.log(f'Current uptime: {uptime} seconds')

    if uptime < uptime_req:
        cp.log(f'Sleeping for {uptime_req - uptime} seconds')  
        time.sleep(uptime_req - uptime)
    
    cp.log('Uptime check passed, continuing...')


def get_sdk_appdata():
    sdk_appdata = cp.get('config/system/sdk/appdata')

    default_appdata = [
        {'name': 'scan_time_sec', 'value': '180'},
        {'name': 'scan_interval_sec', 'value': '10'},
        {'name': 'scan_count', 'value': '15'},
        {'name': 'dwell_time_sec', 'value': '240'}
    ]

    sdk_appdata_names = {item['name'] for item in sdk_appdata}

    for default_item in default_appdata:
        if default_item['name'] not in sdk_appdata_names:
            cp.post('config/system/sdk/appdata', default_item)
            cp.log(f"Added default item: {default_item}")
            sdk_appdata.append(default_item)
        else:
            cp.log(f"Default item already exists: {default_item}")

    for item in sdk_appdata:
        item.pop('_id_', None)

    return sdk_appdata


def get_mdm_wans():
    wans = cp.get('status/wan/devices/')

    mdm_wans = {}
    for k, v in wans.items():
        if k.startswith('mdm-') and v['status']['connection_state'] == 'connected':
            mdm_wans[k] = v['config']['_id_']
        else:
            continue

    return mdm_wans


def wan_select(mdm_wans):
    preferred_mdm_wan = []

    while True:
        sdk_appdata = get_sdk_appdata()
        appdata_dict = {item['name']: int(item['value']) for item in sdk_appdata}
        
        scan_time_sec = appdata_dict.get('scan_time_sec', 180)
        scan_interval_sec = appdata_dict.get('scan_interval_sec', 10)
        scan_count = appdata_dict.get('scan_count', 15)
        dwell_time_sec = appdata_dict.get('dwell_time_sec', 240)
        
        list_length = int(scan_time_sec / scan_interval_sec)
        cp.log(f'Calculated list_length: {list_length}')

        while len(preferred_mdm_wan) < list_length:
            rsrq_values = {}
            for k, v in mdm_wans.items():
                rsrq = cp.get(f'status/wan/devices/{k}/diagnostics/RSRQ')
                rsrq_values[k] = int(rsrq)
            
            cp.log(f'RSRQ values: {rsrq_values}')
            
            sorted_rsrq = sorted(rsrq_values.items(), key=lambda item: item[1], reverse=True)
            
            if sorted_rsrq:
                preferred_mdm_wan.append(sorted_rsrq[0][0])
                cp.log(f'Updated preferred_mdm_wan list: {preferred_mdm_wan}')
            
            time.sleep(scan_interval_sec)

        count = Counter(preferred_mdm_wan)
        if any(value >= scan_count for value in count.values()):
            for key, value in count.items():
                if value >= scan_count:
                    cp.log(f'{key} had better RSRQ for at least {scan_count} of the previous {list_length} scans.')
                    mdm_wan_id = mdm_wans[key]
                    set_rules2_priority(mdm_wan_id, dwell_time_sec)
                    preferred_mdm_wan = []
                    break
        else:
            preferred_mdm_wan.pop(0)
            cp.log(f'Removed oldest entry, updated preferred_mdm_wan list: {preferred_mdm_wan}')


def set_rules2_priority(mdm_wan_id, dwell_time_sec):
    rules2 = cp.get('config/wan/rules2')

    priorities = {rule['_id_']: float(rule['priority']) for rule in rules2}
    lowest_priority = min(priorities.values())

    if priorities.get(mdm_wan_id) == lowest_priority:
        cp.log(f'{mdm_wan_id} already has the lowest priority.')
        return

    for rule in rules2:
        if rule['_id_'] == mdm_wan_id:
            cp.put(f'config/wan/rules2/{mdm_wan_id}/priority', (lowest_priority - .1))
            cp.log(f'Updated {mdm_wan_id} to the lowest priority: {lowest_priority - .1}')
            cp.log(f'Sleeping for {dwell_time_sec} seconds before next iteration')
            time.sleep(dwell_time_sec)
            break


if __name__ == '__main__':
    cp.log('Starting RSRQ WAN Selector')
    check_uptime()
    mdm_wans = get_mdm_wans()
    wan_select(mdm_wans)
            