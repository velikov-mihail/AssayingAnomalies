% Callback function for the slider created in scattermap.m
% Not usable outside this context
%-----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-


global Hslide;
global Ht;
global v1glob;
global v2glob;
global quantiles;
global quanti;
evalv1=[min(v1glob):(max(v1glob)-min(v1glob))/100:max(v1glob)]';
alph=get(Hslide,'Value');
if alph==0
    alph=1;
end;
set(Ht,'String',[num2str(alph),'%']); % update the text box


for i=1:length(quantiles)
        quanti(:,i)=quant(v1glob,v2glob,quantiles(i),alph);
end;
subplot(1,2,2);
hold on;
P=findobj('Color','yellow'); % delete the old curve
delete(P);
for i=1:length(quantiles)
    plot(evalv1,quanti(:,i),'y');
end;

hold off;