% Callback function for the sliders created in sirmap.m
% Not usable outside this context
%-----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-

global direct;
global yinpglob;
global vardir1;
global h1;
global Hslide1;
global Ht1;

global eval1;
global r1;

alph1=get(Hslide1,'Value');
set(Ht1,'String',['a1=' num2str(alph1),'%']); % update the first text box
h1=(alph1/100)*(max(vardir1)-min(vardir1))/2;
if h1==0
    set(Hslide1,'Value',1);
    h1=(get(Hslide1,'Value')/100)*(max(vardir1)-min(vardir1))/2;
end;
warning off;
r1=fastbinsmooth([vardir1';yinpglob'],h1,[min(vardir1),max(vardir1)],201,2,3,0,1);
warning on;
if length(direct)==1
    subplot(1,2,2);
elseif length(direct)==2
    subplot(2,2,2);
end;
hold on;
P=findobj('Color','yellow','LineStyle','-'); % delete the old curves
delete(P);
plot(eval1,r1,'k'); % trace the new curve for Axis2
hold off;
if length(direct)==2
    global vardir2;
    global h2;
    global Hslide2;
    global eval2;
    global r2;
    global Ht2;
    alph2=get(Hslide2,'Value');
    set(Ht2,'String',['a2=' num2str(alph2),'%']); % update the second text box
    h2=(alph2/100)*(max(vardir2)-min(vardir2))/2;
    if h2==0
        set(Hslide2,'Value',1);
        h2=(get(Hslide2,'Value')/100)*(max(vardir2)-min(vardir2))/2;
    end;
    warning off;
    r2=fastbinsmooth([vardir2';yinpglob'],h2,[min(vardir2),max(vardir2)],201,2,3,0,1); % computes the new curve for Axis3
    warning on;
    subplot(2,2,4);
    hold on;
    plot(eval2,r2,'k'); % trace the new curve for Axis3
    hold off;
end;