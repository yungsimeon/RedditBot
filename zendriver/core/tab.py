from __future__ import annotations

import asyncio
import datetime
import logging
import pathlib
import re
import typing
import urllib.parse
import warnings
import webbrowser
from typing import TYPE_CHECKING, Any, List, Literal, Optional, Tuple, Union

from .. import cdp
from . import element, util
from .config import PathLike
from .connection import Connection, ProtocolException

if TYPE_CHECKING:
    from .browser import Browser
    from .element import Element

logger = logging.getLogger(__name__)


class Tab(Connection):
    """
    :ref:`tab` is the controlling mechanism/connection to a 'target',
    for most of us 'target' can be read as 'tab'. however it could also
    be an iframe, serviceworker or background script for example,
    although there isn't much to control for those.

    if you open a new window by using :py:meth:`browser.get(..., new_window=True)`
    your url will open a new window. this window is a 'tab'.
    When you browse to another page, the tab will be the same (it is an browser view).

    So it's important to keep some reference to tab objects, in case you're
    done interacting with elements and want to operate on the page level again.

    Custom CDP commands
    ---------------------------
    Tab object provide many useful and often-used methods. It is also
    possible to utilize the included cdp classes to to something totally custom.

    the cdp package is a set of so-called "domains" with each having methods, events and types.
    to send a cdp method, for example :py:obj:`cdp.page.navigate`, you'll have to check
    whether the method accepts any parameters and whether they are required or not.

    you can use

    ```python
    await tab.send(cdp.page.navigate(url='https://yoururlhere'))
    ```

    so tab.send() accepts a generator object, which is created by calling a cdp method.
    this way you can build very detailed and customized commands.
    (note: finding correct command combo's can be a time consuming task, luckily i added a whole bunch
    of useful methods, preferably having the same api's or lookalikes, as in selenium)


    some useful, often needed and simply required methods
    ===================================================================


    :py:meth:`~find`  |  find(text)
    ----------------------------------------
    find and returns a single element by text match. by default returns the first element found.
    much more powerful is the best_match flag, although also much more expensive.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~find` |  find(text, best_match=True) or find(text, True)
    ---------------------------------------------------------------------------------
    Much more powerful (and expensive!!) than the above, is the use of the `find(text, best_match=True)` flag.
    It will still return 1 element, but when multiple matches are found, picks the one having the
    most similar text length.
    How would that help?
    For example, you search for "login", you'd probably want the "login" button element,
    and not thousands of scripts,meta,headings which happens to contain a string of "login".

    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~select` | select(selector)
    ----------------------------------------
    find and returns a single element by css selector match.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~select_all` | select_all(selector)
    ------------------------------------------------
    find and returns all elements by css selector match.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    await :py:obj:`Tab`
    ---------------------------
    calling `await tab` will do a lot of stuff under the hood, and ensures all references
    are up to date. also it allows for the script to "breathe", as it is oftentime faster than your browser or
    webpage. So whenever you get stuck and things crashes or element could not be found, you should probably let
    it "breathe"  by calling `await page`  and/or `await page.sleep()`

    also, it's ensuring :py:obj:`~url` will be updated to the most recent one, which is quite important in some
    other methods.

    Using other and custom CDP commands
    ======================================================
    using the included cdp module, you can easily craft commands, which will always return an generator object.
    this generator object can be easily sent to the :py:meth:`~send`  method.

    :py:meth:`~send`
    ---------------------------
    this is probably THE most important method, although you won't ever call it, unless you want to
    go really custom. the send method accepts a :py:obj:`cdp` command. Each of which can be found in the
    cdp section.

    when you import * from this package, cdp will be in your namespace, and contains all domains/actions/events
    you can act upon.
    """

    browser: Browser | None
    _download_behavior: List[str] | None = None

    def __init__(
        self,
        websocket_url: str,
        target: cdp.target.TargetInfo,
        browser: Browser | None = None,
        **kwargs,
    ):
        super().__init__(websocket_url, target, browser, **kwargs)
        self.browser = browser
        self._dom = None
        self._window_id = None

    @property
    def inspector_url(self):
        """
        get the inspector url. this url can be used in another browser to show you the devtools interface for
        current tab. useful for debugging (and headless)
        :return:
        :rtype:
        """
        if not self.browser:
            raise ValueError(
                "this tab has no browser attribute, so you can't use inspector_url"
            )

        return f"http://{self.browser.config.host}:{self.browser.config.port}/devtools/inspector.html?ws={self.websocket_url[5:]}"

    def inspector_open(self):
        webbrowser.open(self.inspector_url, new=2)

    async def disable_dom_agent(self):
        # The DOM.disable can throw an exception if not enabled,
        # but if it's already disabled, that's not a "real" error.

        # DOM agent hasn't been enabled
        # command:DOM.disable
        # params:[] [code: -32000]

        # If not ignored, an exception is thrown, and masks other problems
        # (e.g., Could not find node with given id)

        try:
            await self.send(cdp.dom.disable())
        except ProtocolException:
            logger.debug("Ignoring DOM.disable exception", exc_info=True)
            pass

    async def open_external_inspector(self):
        """
        opens the system's browser containing the devtools inspector page
        for this tab. could be handy, especially to debug in headless mode.
        """
        import webbrowser

        webbrowser.open(self.inspector_url)

    async def select(
        self,
        selector: str,
        timeout: Union[int, float] = 10,
    ) -> Element:
        """
        find single element by css selector.
        can also be used to wait for such element to appear.

        :param selector: css selector, eg a[href], button[class*=close], a > img[src]
        :type selector: str

        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int

        """
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        selector = selector.strip()
        item = await self.query_selector(selector)

        while not item:
            await self.wait()
            item = await self.query_selector(selector)
            if loop.time() - start_time > timeout:
                raise asyncio.TimeoutError(
                    "time ran out while waiting for: %s" % selector
                )
            await self.sleep(0.5)
        return item

    async def find(
        self,
        *,
        tagname: str | None = None,
        attrs: dict[str, str] | None = None,
        text: str | None = None,
        timeout: int | float = 10,
    ):
        """
        find single element by text
        can also be used to wait for such element to appear.

        :param tagname: tagname to search for. ex: div, span, input, button..
        :type tagname: str
        :param attrs: attributes to search for. ex: {'class':'class1', 'name':'name1', 'id':'123'}
        :type attrs: dict
        :param text: text to search for. note: script contents are also considered text
        :type text: str
                 since we deal with nodes instead of elements, the find function most often returns
                 so called text nodes, which is actually a element of plain text, which is
                 the somehow imaginary "child" of a "span", "p", "script" or any other elements which have text between their opening
                 and closing tags.
                 most often when we search by text, we actually aim for the element containing the text instead of
                 a lousy plain text node, so by default the containing element is returned.

                 however, there are (why not) exceptions, for example elements that use the "placeholder=" property.
                 this text is rendered, but is not a pure text node. in that case you can set this flag to False.
                 since in this case we are probably interested in just that element, and not it's parent.


                 # todo, automatically determine node type
                 # ignore the return_enclosing_element flag if the found node is NOT a text node but a
                 # regular element (one having a tag) in which case that is exactly what we need.
         :type return_enclosing_element: bool
        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        tagname = tagname.strip().lower() if tagname else None
        attrs = {k.strip(): v.strip() for k, v in attrs.items()} if attrs else None
        text = text.strip().lower() if text else None

        if not text and not tagname and not attrs:
            raise ValueError(
                "You must provide either tagname, attrs, or text to find an element."
            )

        items = await self._find_elements_by_tagname_attrs_text(
            tagname=tagname, attrs=attrs, text=text, return_after_first_match=True
        )
        while not items:
            await self.wait()
            items = await self._find_elements_by_tagname_attrs_text(
                tagname=tagname, attrs=attrs, text=text, return_after_first_match=True
            )
            if loop.time() - start_time > timeout:
                raise asyncio.TimeoutError(
                    f"Time ran out while waiting for element with tagname: {tagname}, attributes: {attrs}, text:{text}"
                )
            await self.sleep(0.5)

        return items[0]

    async def find_all(
        self,
        *,
        tagname: str | None = None,
        attrs: dict[str, str] | None = None,
        text: str | None = None,
        timeout: int | float = 10,
    ) -> List[Element]:
        """
        find multiple elements by text
        can also be used to wait for such element to appear.

        :param tagname: tagname to search for. ex: div, span, input, button..
        :type tagname: str
        :param attrs: attributes to search for. ex: {'class':'class1', 'name':'name1', 'id':'123'}
        :type attrs: dict
        :param text: text to search for. note: script contents are also considered text
        :type text: str

        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """

        loop = asyncio.get_running_loop()
        start_time = loop.time()

        tagname = tagname.strip().lower() if tagname else None
        attrs = {k.strip(): v.strip() for k, v in attrs.items()} if attrs else None
        text = text.strip().lower() if text else None

        if not text and not tagname and not attrs:
            # raising an error in case neither text nor tagname values were provided
            raise ValueError(
                "You must provide either tagname, attrs, or text to find elements."
            )

        items = await self._find_elements_by_tagname_attrs_text(
            tagname=tagname, attrs=attrs, text=text, return_after_first_match=False
        )
        while not items:
            await self.wait()
            items = await self._find_elements_by_tagname_attrs_text(
                tagname=tagname, attrs=attrs, text=text, return_after_first_match=False
            )
            if loop.time() - start_time > timeout:
                raise asyncio.TimeoutError(
                    f"Time ran out while waiting for elements with tagname: {tagname}, attributess: {attrs}, text: {text}"
                )
            await self.sleep(0.5)

        return items

    async def select_all(
        self, selector: str, timeout: Union[int, float] = 10, include_frames=False
    ) -> List[Element]:
        """
        find multiple elements by css selector.
        can also be used to wait for such element to appear.


        :param selector: css selector, eg a[href], button[class*=close], a > img[src]
        :type selector: str
        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        :param include_frames: whether to include results in iframes.
        :type include_frames: bool
        """

        loop = asyncio.get_running_loop()
        now = loop.time()
        selector = selector.strip()
        items = []
        if include_frames:
            frames = await self.query_selector_all("iframe")
            # unfortunately, asyncio.gather here is not an option
            for fr in frames:
                items.extend(await fr.query_selector_all(selector))

        items.extend(await self.query_selector_all(selector))
        while not items:
            await self.wait()
            items = await self.query_selector_all(selector)
            if loop.time() - now > timeout:
                raise asyncio.TimeoutError(
                    "time ran out while waiting for: %s" % selector
                )
            await self.sleep(0.5)
        return items

    async def get(
        self, url="chrome://welcome", new_tab: bool = False, new_window: bool = False
    ):
        """top level get. utilizes the first tab to retrieve given url.

        convenience function known from selenium.
        this function handles waits/sleeps and detects when DOM events fired, so it's the safest
        way of navigating.

        :param url: the url to navigate to
        :param new_tab: open new tab
        :param new_window:  open new window
        :return: Page
        """
        if not self.browser:
            raise AttributeError(
                "this page/tab has no browser attribute, so you can't use get()"
            )
        if new_window and not new_tab:
            new_tab = True

        if new_tab:
            return await self.browser.get(url, new_tab, new_window)
        else:
            await self.send(cdp.page.navigate(url))
            await self.wait()
            return self

    async def find_element_by_text(
        self,
        text: str,
    ) -> Element | None:
        """
        finds and returns the first element containing <text>, or best match

        :param text:
        :type text:
        :return:
        :rtype:
        """
        if not text:
            raise ValueError("You must provide a text value to find an element with.")

        return await self.find(text=text)

    async def find_elements_by_text(
        self,
        text: str,
    ) -> list[Element]:
        """
        returns element which match the given text.
        please note: this may (or will) also return any other element (like inline scripts),
        which happen to contain that text.

        :param text:
        :type text:
        :return:
        :rtype:
        """
        if not text:
            raise ValueError("You must provide a text value to find elements with.")

        return await self.find_all(text=text)

    async def _find_elements_by_tagname_attrs_text(
        self,
        tagname: str | None = None,
        attrs: dict[str, str] | None = None,
        text: str | None = None,
        return_after_first_match: bool = False,
    ) -> list[Element]:
        """
        Finds and returns all elements matching the tagname, attributes, and optional innerText.

        :param tagname: The name of the HTML tag to search for (e.g., 'button', 'input'). Optional.
        :type tagname: str | None
        :param attrs: A dictionary of attributes and their corresponding values to match. Optional.
        :type attrs: dict[str, str] | None
        :param text: The expected text value of the element. Optional.
        :type text: str | None
        :param return_after_first_match: If True, stops traversal and returns a list containing only the first matching element.
        :type return_after_first_match: bool
        :return: List of matching elements. If return_after_first_match is True, the list contains at most one element.
        :rtype: list[Element]
        """

        elements = []
        stop_searching = False  # flag to indicate whether to stop searching

        async def traverse(node, parent_tree):
            """Recursive traversal of the DOM and shadow DOM to collect all matching elements."""

            nonlocal stop_searching

            if not node or stop_searching:
                return

            # create an element to check for the conditions we're looking for
            elem = element.create(node, self, parent_tree)

            # check for conditions
            matches_tagname = (
                not tagname
                or (elem.tag_name and tagname == elem.tag_name.strip().lower())
            )  # this condition evaluates to True if tagname was not provided; no filtering by tagname. Or if tagname equals our targeted element's tagname

            matches_attrs = (
                not attrs
                or (
                    elem.attributes
                    and all(
                        any(
                            elem.attributes[i] == attr
                            and value in elem.attributes[i + 1].split()
                            for i in range(0, len(elem.attributes), 2)
                        )
                        for attr, value in attrs.items()
                    )
                )
            )  # this condition evaluates to True if attrs was not provided; no filtering by attrs. Or if the provided attrs are in our targeted element's attributes

            matches_text = (
                not text or (elem.text and text in elem.text.strip().lower())
            )  # this condition evaluates to True if text was not provided; no filtering by text. Or if text is in our targeted element's text

            # if all conditions match, add the element to the list of elements to return
            if matches_tagname and matches_attrs and matches_text:
                # sometimes the parent element is preceived as the element holding the text content while it actually the child that does so, below is the code to handle that situation
                if (
                    text and matches_text and elem.children
                ):  # we only check for children containing the text if text was provided and elem.children exists
                    # if elem.children:
                    for child in elem.children:
                        if text in child.text.strip().lower():
                            elem = child
                            break
                elements.append(elem)
                if return_after_first_match:  # if return_after_first_match is True then we stop searching for other elements after finding one target element
                    stop_searching = (
                        True  # set the flag to True to stop further traversal
                    )
                    return

            # if stop_searching is True, skip further traversal
            if stop_searching:
                return

            tasks: list[asyncio.Task] = []

            # traverse shadow roots nodes
            if node.shadow_roots:
                tasks.extend(
                    traverse(shadow_root, parent_tree)
                    for shadow_root in node.shadow_roots
                )

            # traverse child nodes
            if node.children:
                tasks.extend(traverse(child, parent_tree) for child in node.children)

            await asyncio.gather(*tasks)

        # fetch the document root
        doc = await self.send(cdp.dom.get_document(depth=-1, pierce=True))

        # start traversing the DOM tree
        await traverse(doc, doc)

        # search within iframes concurrently
        if not stop_searching:  # only search iframes if we haven't found a match yet
            iframes = util.filter_recurse_all(
                doc, lambda node: node.node_name == "IFRAME"
            )
            iframe_tasks = [
                traverse(iframe.content_document, iframe.content_document)
                for iframe in iframes
                if iframe.content_document
            ]

            if iframe_tasks:
                await asyncio.gather(*iframe_tasks)

        # return the appropriate result
        if return_after_first_match:
            return elements[
                :1
            ]  # return a list containing only the first element (or empty list if no match)
        else:
            return elements  # return all matching elements

    async def query_selector_all(
        self,
        selector: str,
        _node: cdp.dom.Node | Element | None = None,
    ):
        """
        equivalent of javascripts document.querySelectorAll.
        this is considered one of the main methods to use in this package.

        it returns all matching :py:obj:`zendriver.Element` objects.

        :param selector: css selector. (first time? => https://www.w3schools.com/cssref/css_selectors.php )
        :type selector: str
        :param _node: internal use
        :type _node:
        :return:
        :rtype:
        """
        doc: Any
        if not _node:
            doc = await self.send(cdp.dom.get_document(-1, True))
        else:
            doc = _node
            if _node.node_name == "IFRAME":
                doc = _node.content_document
        node_ids = []

        try:
            node_ids = await self.send(
                cdp.dom.query_selector_all(doc.node_id, selector)
            )
        except ProtocolException as e:
            if _node is not None:
                if e.message is not None and "could not find node" in e.message.lower():
                    if getattr(_node, "__last", None):
                        delattr(_node, "__last")
                        return []
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    if isinstance(_node, Element):
                        await _node.update()
                    # make sure this isn't turned into infinite loop
                    setattr(_node, "__last", True)
                    return await self.query_selector_all(selector, _node)
            else:
                await self.disable_dom_agent()
                raise
        if not node_ids:
            return []
        items = []

        for nid in node_ids:
            node = util.filter_recurse(doc, lambda n: n.node_id == nid)
            # we pass along the retrieved document tree,
            # to improve performance
            if not node:
                continue
            elem = element.create(node, self, doc)
            items.append(elem)

        return items

    async def query_selector(
        self,
        selector: str,
        _node: Optional[Union[cdp.dom.Node, Element]] = None,
    ):
        """
        find single element based on css selector string

        :param selector: css selector(s)
        :type selector: str
        :return:
        :rtype:
        """
        selector = selector.strip()

        doc: Any
        if not _node:
            doc = await self.send(cdp.dom.get_document(-1, True))
        else:
            doc = _node
            if _node.node_name == "IFRAME":
                doc = _node.content_document
        node_id = None

        try:
            node_id = await self.send(cdp.dom.query_selector(doc.node_id, selector))

        except ProtocolException as e:
            if _node is not None:
                if e.message is not None and "could not find node" in e.message.lower():
                    if getattr(_node, "__last", None):
                        delattr(_node, "__last")
                        return []
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    if isinstance(_node, Element):
                        await _node.update()
                    # make sure this isn't turned into infinite loop
                    setattr(_node, "__last", True)
                    return await self.query_selector(selector, _node)
            else:
                await self.disable_dom_agent()
                raise
        if not node_id:
            return
        node = util.filter_recurse(doc, lambda n: n.node_id == node_id)
        if not node:
            return
        return element.create(node, self, doc)

    async def back(self):
        """
        history back
        """
        await self.send(cdp.runtime.evaluate("window.history.back()"))

    async def forward(self):
        """
        history forward
        """
        await self.send(cdp.runtime.evaluate("window.history.forward()"))

    async def reload(
        self,
        ignore_cache: Optional[bool] = True,
        script_to_evaluate_on_load: Optional[str] = None,
    ):
        """
        Reloads the page

        :param ignore_cache: when set to True (default), it ignores cache, and re-downloads the items
        :type ignore_cache:
        :param script_to_evaluate_on_load: script to run on load. I actually haven't experimented with this one, so no guarantees.
        :type script_to_evaluate_on_load:
        :return:
        :rtype:
        """
        await self.send(
            cdp.page.reload(
                ignore_cache=ignore_cache,
                script_to_evaluate_on_load=script_to_evaluate_on_load,
            ),
        )

    async def evaluate(
        self, expression: str, await_promise=False, return_by_value=True
    ):
        remote_object, errors = await self.send(
            cdp.runtime.evaluate(
                expression=expression,
                user_gesture=True,
                await_promise=await_promise,
                return_by_value=return_by_value,
                allow_unsafe_eval_blocked_by_csp=True,
            )
        )
        if errors:
            raise ProtocolException(errors)

        if remote_object:
            if return_by_value:
                if remote_object.value:
                    return remote_object.value

            else:
                return remote_object, errors

    async def js_dumps(
        self, obj_name: str, return_by_value: Optional[bool] = True
    ) -> (
        dict
        | typing.Tuple[cdp.runtime.RemoteObject, cdp.runtime.ExceptionDetails | None]
    ):
        """
        dump given js object with its properties and values as a dict

        note: complex objects might not be serializable, therefore this method is not a "source of thruth"

        :param obj_name: the js object to dump
        :type obj_name: str

        :param return_by_value: if you want an tuple of cdp objects (returnvalue, errors), set this to False
        :type return_by_value: bool

        example
        ------

        x = await self.js_dumps('window')
        print(x)
            '...{
            'pageYOffset': 0,
            'visualViewport': {},
            'screenX': 10,
            'screenY': 10,
            'outerWidth': 1050,
            'outerHeight': 832,
            'devicePixelRatio': 1,
            'screenLeft': 10,
            'screenTop': 10,
            'styleMedia': {},
            'onsearch': None,
            'isSecureContext': True,
            'trustedTypes': {},
            'performance': {'timeOrigin': 1707823094767.9,
            'timing': {'connectStart': 0,
            'navigationStart': 1707823094768,
            ]...
            '
        """
        js_code_a = (
            """
                           function ___dump(obj, _d = 0) {
                               let _typesA = ['object', 'function'];
                               let _typesB = ['number', 'string', 'boolean'];
                               if (_d == 2) {
                                   console.log('maxdepth reached for ', obj);
                                   return
                               }
                               let tmp = {}
                               for (let k in obj) {
                                   if (obj[k] == window) continue;
                                   let v;
                                   try {
                                       if (obj[k] === null || obj[k] === undefined || obj[k] === NaN) {
                                           console.log('obj[k] is null or undefined or Nan', k, '=>', obj[k])
                                           tmp[k] = obj[k];
                                           continue
                                       }
                                   } catch (e) {
                                       tmp[k] = null;
                                       continue
                                   }


                                   if (_typesB.includes(typeof obj[k])) {
                                       tmp[k] = obj[k]
                                       continue
                                   }

                                   try {
                                       if (typeof obj[k] === 'function') {
                                           tmp[k] = obj[k].toString()
                                           continue
                                       }


                                       if (typeof obj[k] === 'object') {
                                           tmp[k] = ___dump(obj[k], _d + 1);
                                           continue
                                       }


                                   } catch (e) {}

                                   try {
                                       tmp[k] = JSON.stringify(obj[k])
                                       continue
                                   } catch (e) {

                                   }
                                   try {
                                       tmp[k] = obj[k].toString();
                                       continue
                                   } catch (e) {}
                               }
                               return tmp
                           }

                           function ___dumpY(obj) {
                               var objKeys = (obj) => {
                                   var [target, result] = [obj, []];
                                   while (target !== null) {
                                       result = result.concat(Object.getOwnPropertyNames(target));
                                       target = Object.getPrototypeOf(target);
                                   }
                                   return result;
                               }
                               return Object.fromEntries(
                                   objKeys(obj).map(_ => [_, ___dump(obj[_])]))

                           }
                           ___dumpY( %s )
                   """
            % obj_name
        )
        js_code_b = (
            """
            ((obj, visited = new WeakSet()) => {
                 if (visited.has(obj)) {
                     return {}
                 }
                 visited.add(obj)
                 var result = {}, _tmp;
                 for (var i in obj) {
                         try {
                             if (i === 'enabledPlugin' || typeof obj[i] === 'function') {
                                 continue;
                             } else if (typeof obj[i] === 'object') {
                                 _tmp = recurse(obj[i], visited);
                                 if (Object.keys(_tmp).length) {
                                     result[i] = _tmp;
                                 }
                             } else {
                                 result[i] = obj[i];
                             }
                         } catch (error) {
                             // console.error('Error:', error);
                         }
                     }
                return result;
            })(%s)
        """
            % obj_name
        )

        # we're purposely not calling self.evaluate here to prevent infinite loop on certain expressions
        remote_object, exception_details = await self.send(
            cdp.runtime.evaluate(
                js_code_a,
                await_promise=True,
                return_by_value=return_by_value,
                allow_unsafe_eval_blocked_by_csp=True,
            )
        )
        if exception_details:
            # try second variant

            remote_object, exception_details = await self.send(
                cdp.runtime.evaluate(
                    js_code_b,
                    await_promise=True,
                    return_by_value=return_by_value,
                    allow_unsafe_eval_blocked_by_csp=True,
                )
            )

        if exception_details:
            raise ProtocolException(exception_details)
        if return_by_value and remote_object.value:
            return remote_object.value
        else:
            return remote_object, exception_details

    async def close(self):
        """
        close the current target (ie: tab,window,page)
        :return:
        :rtype:
        """
        if self.target and self.target.target_id:
            await self.send(cdp.target.close_target(target_id=self.target.target_id))

    async def get_window(self) -> Tuple[cdp.browser.WindowID, cdp.browser.Bounds]:
        """
        get the window Bounds
        :return:
        :rtype:
        """
        window_id, bounds = await self.send(
            cdp.browser.get_window_for_target(self.target_id)
        )
        return window_id, bounds

    async def get_content(self):
        """
        gets the current page source content (html)
        :return:
        :rtype:
        """
        doc: cdp.dom.Node = await self.send(cdp.dom.get_document(-1, True))
        return await self.send(
            cdp.dom.get_outer_html(backend_node_id=doc.backend_node_id)
        )

    async def maximize(self):
        """
        maximize page/tab/window
        """
        return await self.set_window_state(state="maximize")

    async def minimize(self):
        """
        minimize page/tab/window
        """
        return await self.set_window_state(state="minimize")

    async def fullscreen(self):
        """
        minimize page/tab/window
        """
        return await self.set_window_state(state="fullscreen")

    async def medimize(self):
        return await self.set_window_state(state="normal")

    async def set_window_size(self, left=0, top=0, width=1280, height=1024):
        """
        set window size and position

        :param left: pixels from the left of the screen to the window top-left corner
        :type left:
        :param top: pixels from the top of the screen to the window top-left corner
        :type top:
        :param width: width of the window in pixels
        :type width:
        :param height: height of the window in pixels
        :type height:
        :return:
        :rtype:
        """
        return await self.set_window_state(left, top, width, height)

    async def activate(self):
        """
        active this target (ie: tab,window,page)
        """
        if self.target is None:
            raise ValueError("target is none")
        await self.send(cdp.target.activate_target(self.target.target_id))

    async def bring_to_front(self):
        """
        alias to self.activate
        """
        await self.activate()

    async def set_window_state(
        self, left=0, top=0, width=1280, height=720, state="normal"
    ):
        """
        sets the window size or state.

        for state you can provide the full name like minimized, maximized, normal, fullscreen, or
        something which leads to either of those, like min, mini, mi,  max, ma, maxi, full, fu, no, nor
        in case state is set other than "normal", the left, top, width, and height are ignored.

        :param left:
            desired offset from left, in pixels
        :type left: int

        :param top:
            desired offset from the top, in pixels
        :type top: int

        :param width:
            desired width in pixels
        :type width: int

        :param height:
            desired height in pixels
        :type height: int

        :param state:
            can be one of the following strings:
                - normal
                - fullscreen
                - maximized
                - minimized

        :type state: str

        """
        available_states = ["minimized", "maximized", "fullscreen", "normal"]
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = await self.get_window()

        for state_name in available_states:
            if all(x in state_name for x in state.lower()):
                break
        else:
            raise NameError(
                "could not determine any of %s from input '%s'"
                % (",".join(available_states), state)
            )
        window_state = getattr(
            cdp.browser.WindowState, state_name.upper(), cdp.browser.WindowState.NORMAL
        )
        if window_state == cdp.browser.WindowState.NORMAL:
            bounds = cdp.browser.Bounds(left, top, width, height, window_state)
        else:
            # min, max, full can only be used when current state == NORMAL
            # therefore we first switch to NORMAL
            await self.set_window_state(state="normal")
            bounds = cdp.browser.Bounds(window_state=window_state)

        await self.send(cdp.browser.set_window_bounds(window_id, bounds=bounds))

    async def scroll_down(self, amount=25):
        """
        scrolls down maybe

        :param amount: number in percentage. 25 is a quarter of page, 50 half, and 1000 is 10x the page
        :type amount: int
        :return:
        :rtype:
        """
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = await self.get_window()

        await self.send(
            cdp.input_.synthesize_scroll_gesture(
                x=0,
                y=0,
                y_distance=-(bounds.height * (amount / 100)),
                y_overscroll=0,
                x_overscroll=0,
                prevent_fling=True,
                repeat_delay_ms=0,
                speed=7777,
            )
        )

    async def scroll_up(self, amount=25):
        """
        scrolls up maybe

        :param amount: number in percentage. 25 is a quarter of page, 50 half, and 1000 is 10x the page
        :type amount: int

        :return:
        :rtype:
        """
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = await self.get_window()

        await self.send(
            cdp.input_.synthesize_scroll_gesture(
                x=0,
                y=0,
                y_distance=(bounds.height * (amount / 100)),
                x_overscroll=0,
                prevent_fling=True,
                repeat_delay_ms=0,
                speed=7777,
            )
        )

    async def wait_for(
        self,
        tagname: Optional[str] = None,
        attrs: Optional[dict[str, str]] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        timeout: int | float = 10,
    ) -> element.Element:
        """
        variant on query_selector_all and find_elements_by_text
        this variant takes either selector or text, and will block until
        the requested element(s) are found.

        it will block for a maximum of <timeout> seconds, after which
        an TimeoutError will be raised

        :param tagname: element tagname
        :type tagname: str
        :param attrs: dictionary of attributes
        :type attrs: dictionary
        :param selector: css selector
        :type selector:
        :param text: text
        :type text:
        :param timeout:
        :type timeout:
        :return:
        :rtype: Element
        :raises: asyncio.TimeoutError
        """
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        if (
            tagname or attrs or text
        ):  # waiting for an element using either their tagname, attributes, text, or all.
            if not tagname:
                tagname = None
            if not attrs:
                attrs = None
            if not text:
                text = None

            item = await self.find(tagname=tagname, attrs=attrs, text=text)
            while not item and loop.time() - start_time < timeout:
                item = await self.find(tagname=tagname, attrs=attrs, text=text)
                await self.sleep(0.5)

            if item:
                return item

        if selector:
            item = await self.query_selector(selector)
            while not item and loop.time() - start_time < timeout:
                item = await self.query_selector(selector)
                await self.sleep(0.5)

            if item:
                return item

        raise asyncio.TimeoutError("Time ran out while waiting.")

    async def wait_for_ready_state(
        self,
        until: Literal["loading", "interactive", "complete"] = "interactive",
        timeout: int = 10,
    ):
        """
        Waits for the page to reach a certain ready state.

        :param until: The ready state to wait for. Can be one of "loading", "interactive", or "complete".
        :type until: str
        :param timeout: The maximum number of seconds to wait.
        :type timeout: int
        :raises asyncio.TimeoutError: If the timeout is reached before the ready state is reached.
        :return: True if the ready state is reached.
        :rtype: bool
        """
        loop = asyncio.get_event_loop()
        start_time = loop.time()

        while True:
            ready_state = await self.evaluate("document.readyState")
            if ready_state == until:
                return True

            if loop.time() - start_time > timeout:
                raise asyncio.TimeoutError(
                    "time ran out while waiting for load page until %s" % until
                )

            await asyncio.sleep(0.1)

    def expect_request(
        self, url_pattern: Union[str, re.Pattern[str]]
    ) -> "RequestExpectation":
        """
        Creates a request expectation for a specific URL pattern.

        :param url_pattern: The URL pattern to match requests.
        :type url_pattern: Union[str, re.Pattern[str]]
        :return: A RequestExpectation instance.
        :rtype: RequestExpectation
        """
        return RequestExpectation(self, url_pattern)

    def expect_response(
        self, url_pattern: Union[str, re.Pattern[str]]
    ) -> "ResponseExpectation":
        """
        Creates a response expectation for a specific URL pattern.

        :param url_pattern: The URL pattern to match responses.
        :type url_pattern: Union[str, re.Pattern[str]]
        :return: A ResponseExpectation instance.
        :rtype: ResponseExpectation
        """
        return ResponseExpectation(self, url_pattern)

    async def download_file(self, url: str, filename: Optional[PathLike] = None):
        """
        downloads file by given url.

        :param url: url of the file
        :param filename: the name for the file. if not specified the name is composed from the url file name
        """
        if not self._download_behavior:
            directory_path = pathlib.Path.cwd() / "downloads"
            directory_path.mkdir(exist_ok=True)
            await self.set_download_path(directory_path)

            warnings.warn(
                f"no download path set, so creating and using a default of"
                f"{directory_path}"
            )
        if not filename:
            filename = url.rsplit("/")[-1]
            filename = filename.split("?")[0]

        code = """
         (elem) => {
            async function _downloadFile(
              imageSrc,
              nameOfDownload,
            ) {
              const response = await fetch(imageSrc);
              const blobImage = await response.blob();
              const href = URL.createObjectURL(blobImage);

              const anchorElement = document.createElement('a');
              anchorElement.href = href;
              anchorElement.download = nameOfDownload;

              document.body.appendChild(anchorElement);
              anchorElement.click();

              setTimeout(() => {
                document.body.removeChild(anchorElement);
                window.URL.revokeObjectURL(href);
                }, 500);
            }
            _downloadFile('%s', '%s')
            }
            """ % (
            url,
            filename,
        )

        body = (await self.query_selector_all("body"))[0]
        await body.update()
        await self.send(
            cdp.runtime.call_function_on(
                code,
                object_id=body.object_id,
                arguments=[cdp.runtime.CallArgument(object_id=body.object_id)],
            )
        )

    async def save_screenshot(
        self,
        filename: Optional[PathLike] = "auto",
        format: str = "jpeg",
        full_page: bool = False,
    ) -> str:
        """
        Saves a screenshot of the page.
        This is not the same as :py:obj:`Element.save_screenshot`, which saves a screenshot of a single element only

        :param filename: uses this as the save path
        :type filename: PathLike
        :param format: jpeg or png (defaults to jpeg)
        :type format: str
        :param full_page: when False (default) it captures the current viewport. when True, it captures the entire page
        :type full_page: bool
        :return: the path/filename of saved screenshot
        :rtype: str
        """
        if self.target is None:
            raise ValueError("target is none")

        await self.sleep()  # update the target's url
        path = None

        if format.lower() in ["jpg", "jpeg"]:
            ext = ".jpg"
            format = "jpeg"

        elif format.lower() in ["png"]:
            ext = ".png"
            format = "png"

        if not filename or filename == "auto":
            parsed = urllib.parse.urlparse(self.target.url)
            parts = parsed.path.split("/")
            last_part = parts[-1]
            last_part = last_part.rsplit("?", 1)[0]
            dt_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            candidate = f"{parsed.hostname}__{last_part}_{dt_str}"
            path = pathlib.Path(candidate + ext)  # noqa
        else:
            path = pathlib.Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = await self.send(
            cdp.page.capture_screenshot(
                format_=format, capture_beyond_viewport=full_page
            )
        )
        if not data:
            raise ProtocolException(
                "could not take screenshot. most possible cause is the page has not finished loading yet."
            )
        import base64

        data_bytes = base64.b64decode(data)
        if not path:
            raise RuntimeError("invalid filename or path: '%s'" % filename)
        path.write_bytes(data_bytes)
        return str(path)

    async def set_download_path(self, path: PathLike):
        """
        sets the download path and allows downloads
        this is required for any download function to work (well not entirely, since when unset we set a default folder)

        :param path:
        :type path:
        :return:
        :rtype:
        """
        path = pathlib.Path(path)
        await self.send(
            cdp.browser.set_download_behavior(
                behavior="allow", download_path=str(path.resolve())
            )
        )
        self._download_behavior = ["allow", str(path.resolve())]

    async def get_all_linked_sources(self) -> List[Element]:
        """
        get all elements of tag: link, a, img, scripts meta, video, audio

        :return:
        """
        all_assets = await self.query_selector_all(selector="a,link,img,script,meta")
        return [element.create(asset, self) for asset in all_assets]

    async def get_all_urls(self, absolute=True) -> List[str]:
        """
        convenience function, which returns all links (a,link,img,script,meta)

        :param absolute: try to build all the links in absolute form instead of "as is", often relative
        :return: list of urls
        """

        import urllib.parse

        res = []
        all_assets = await self.query_selector_all(selector="a,link,img,script,meta")
        for asset in all_assets:
            if not absolute:
                res.append(asset.src or asset.href)
            else:
                for k, v in asset.attrs.items():
                    if k in ("src", "href"):
                        if "#" in v:
                            continue
                        if not any([_ in v for _ in ("http", "//", "/")]):
                            continue
                        abs_url = urllib.parse.urljoin(
                            "/".join(self.url.rsplit("/")[:3]), v
                        )
                        if not abs_url.startswith(("http", "//", "ws")):
                            continue
                        res.append(abs_url)
        return res

    async def verify_cf(self):
        """an attempt.."""
        checkbox = None
        checkbox_sibling = await self.wait_for(text="verify you are human")
        if checkbox_sibling:
            parent = checkbox_sibling.parent
            while parent:
                checkbox = await parent.query_selector("input[type=checkbox]")
                if checkbox:
                    break
                parent = parent.parent
        if not checkbox:
            raise RuntimeError("could not find checkbox for cloudflare verification")
        await checkbox.mouse_move()
        await checkbox.mouse_click()

    async def get_local_storage(self):
        """
        get local storage items as dict of strings (careful!, proper deserialization needs to be done if needed)

        :return:
        :rtype:
        """
        if self.target is None or not self.target.url:
            await self.wait()

        # there must be a better way...
        origin = "/".join(self.url.split("/", 3)[:-1])

        items = await self.send(
            cdp.dom_storage.get_dom_storage_items(
                cdp.dom_storage.StorageId(is_local_storage=True, security_origin=origin)
            )
        )
        retval = {}
        for item in items:
            retval[item[0]] = item[1]
        return retval

    async def set_local_storage(self, items: dict):
        """
        set local storage.
        dict items must be strings. simple types will be converted to strings automatically.

        :param items: dict containing {key:str, value:str}
        :type items: dict[str,str]
        :return:
        :rtype:
        """
        if self.target is None or not self.target.url:
            await self.wait()
        # there must be a better way...
        origin = "/".join(self.url.split("/", 3)[:-1])

        await asyncio.gather(
            *[
                self.send(
                    cdp.dom_storage.set_dom_storage_item(
                        storage_id=cdp.dom_storage.StorageId(
                            is_local_storage=True, security_origin=origin
                        ),
                        key=str(key),
                        value=str(val),
                    )
                )
                for key, val in items.items()
            ]
        )

    async def set_user_agent(
        self,
        user_agent: str | None = None,
        accept_language: str | None = None,
        platform: str | None = None,
    ) -> None:
        """
        Set the user agent, accept language, and platform.

        These correspond to:
            - navigator.userAgent
            - navigator.language
            - navigator.platform

        :param user_agent: user agent string
        :type user_agent: str
        :param accept_language: accept language string
        :type accept_language: str
        :param platform: platform string
        :type platform: str
        :return:
        :rtype:
        """
        if not user_agent:
            user_agent = await self.evaluate("navigator.userAgent")
            if not user_agent:
                raise ValueError(
                    "Could not read existing user agent from navigator object"
                )

        await self.send(
            cdp.network.set_user_agent_override(
                user_agent=user_agent,
                accept_language=accept_language,
                platform=platform,
            )
        )

    def __call__(
        self,
        tagname: str | None = None,
        attrs: dict[str, str] | None = None,
        text: str | None = None,
        selector: str | None = None,
        timeout: int | float = 10,
    ):
        """
        alias to query_selector_all or find_elements_by_text, depending
        on whether text= is set or selector= is set

        :param selector: css selector string
        :type selector: str
        :return:
        :rtype:
        """
        return self.wait_for(
            tagname=tagname, attrs=attrs, text=text, selector=selector, timeout=timeout
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Tab):
            return False

        return other.target == self.target

    def __getattr__(self, item):
        try:
            return getattr(self._target, item)
        except AttributeError:
            raise AttributeError(
                f'"{self.__class__.__name__}" has no attribute "%s"' % item
            )

    def __repr__(self):
        extra = ""
        if self.target is not None and self.target.url:
            extra = f"[url: {self.target.url}]"
        s = f"<{type(self).__name__} [{self.target_id}] [{self.type_}] {extra}>"
        return s


class BaseRequestExpectation:
    """
    Base class for handling request and response expectations.

    This class provides a context manager to wait for specific network requests and responses
    based on a URL pattern. It sets up handlers for request and response events and provides
    properties to access the request, response, and response body.

    :param tab: The Tab instance to monitor.
    :type tab: Tab
    :param url_pattern: The URL pattern to match requests and responses.
    :type url_pattern: Union[str, re.Pattern[str]]
    """

    def __init__(self, tab: Tab, url_pattern: Union[str, re.Pattern[str]]):
        self.tab = tab
        self.url_pattern = url_pattern
        self.request_future: asyncio.Future[cdp.network.RequestWillBeSent] = (
            asyncio.Future()
        )
        self.response_future: asyncio.Future[cdp.network.ResponseReceived] = (
            asyncio.Future()
        )
        self.request_id: Union[cdp.network.RequestId, None] = None

    async def _request_handler(self, event: cdp.network.RequestWillBeSent):
        """
        Internal handler for request events.

        :param event: The request event.
        :type event: cdp.network.RequestWillBeSent
        """
        if re.fullmatch(self.url_pattern, event.request.url):
            self._remove_request_handler()
            self.request_id = event.request_id
            self.request_future.set_result(event)

    async def _response_handler(self, event: cdp.network.ResponseReceived):
        """
        Internal handler for response events.

        :param event: The response event.
        :type event: cdp.network.ResponseReceived
        """
        if event.request_id == self.request_id:
            self._remove_response_handler()
            self.response_future.set_result(event)

    def _remove_request_handler(self):
        """
        Remove the request event handler.
        """
        self.tab.remove_handlers(cdp.network.RequestWillBeSent, self._request_handler)

    def _remove_response_handler(self):
        """
        Remove the response event handler.
        """
        self.tab.remove_handlers(cdp.network.ResponseReceived, self._response_handler)

    async def __aenter__(self):
        """
        Enter the context manager, adding request and response handlers.
        """
        self.tab.add_handler(cdp.network.RequestWillBeSent, self._request_handler)
        self.tab.add_handler(cdp.network.ResponseReceived, self._response_handler)
        return self

    async def __aexit__(self, *args):
        """
        Exit the context manager, removing request and response handlers.
        """
        self._remove_request_handler()
        self._remove_response_handler()

    @property
    async def request(self):
        """
        Get the matched request.

        :return: The matched request.
        :rtype: cdp.network.Request
        """
        return (await self.request_future).request

    @property
    async def response(self):
        """
        Get the matched response.

        :return: The matched response.
        :rtype: cdp.network.Response
        """
        return (await self.response_future).response

    @property
    async def response_body(self):
        """
        Get the body of the matched response.

        :return: The response body.
        :rtype: str
        """
        request_id = (await self.request_future).request_id
        body = await self.tab.send(cdp.network.get_response_body(request_id=request_id))
        return body


class RequestExpectation(BaseRequestExpectation):
    """
    Class for handling request expectations.

    This class extends `BaseRequestExpectation` and provides a property to access the matched request.

    :param tab: The Tab instance to monitor.
    :type tab: Tab
    :param url_pattern: The URL pattern to match requests.
    :type url_pattern: Union[str, re.Pattern[str]]
    """

    @property
    async def value(self) -> cdp.network.RequestWillBeSent:
        """
        Get the matched request event.

        :return: The matched request event.
        :rtype: cdp.network.RequestWillBeSent
        """
        return await self.request_future


class ResponseExpectation(BaseRequestExpectation):
    """
    Class for handling response expectations.

    This class extends `BaseRequestExpectation` and provides a property to access the matched response.

    :param tab: The Tab instance to monitor.
    :type tab: Tab
    :param url_pattern: The URL pattern to match responses.
    :type url_pattern: Union[str, re.Pattern[str]]
    """

    @property
    async def value(self) -> cdp.network.ResponseReceived:
        """
        Get the matched response event.

        :return: The matched response event.
        :rtype: cdp.network.ResponseReceived
        """
        return await self.response_future
