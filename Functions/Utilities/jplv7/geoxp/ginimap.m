function [out]=ginimap(long,lat,variable,varargin)
% PURPOSE: This function links a map and a Lorentz Curve
%------------------------------------------------------------------------
% USAGE: out=ginimap(long,lat,variable,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           variable = n x 1 vector of the variable to study
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on  the gini plot by clicking with the left mouse button
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses gini.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
name=inputname(3);
%creation d'un menu pour sauver
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save boxplotfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
c=0;
l=0;
symbol=0;
% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    end;
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%

% compute Gini index and the parameters
[f,F,g,G,GINI]=gini(variable);
vsort=sort(variable);
N=histc(variable,vsort');
Xk=vsort(find(N~=0));
FuncF=cumsum(f);
FuncG=cumsum(g);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Trace the gini plot
Axis2=subplot(1,2,2);
plot(F,G);
title(name);
Ht=uicontrol('Style','text','String',['Gini index:',num2str(GINI)],'Enable','inactive');
set(Ht,'Units','normalized');

set(Ht,'Position',[0.64,0.02,0.15,0.025])

xlabel('F');
ylabel('G');
axis square;
axis manual;
hold on;
plot(F,F,'r');
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Main loop
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    plot(F,F,'r');
    plot(F,G);
    set(Axis2,'xtick',[0,0.5,1],'ytick',[0,0.5,1]);
    axis manual;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iselect)
        xlab=sort([0,0.5,1,x]);
        ylab=sort([0,0.5,GG]);
        set(Axis2,'xtick',xlab,'ytick',ylab);
        line([[x;x],[0;x]],[[0;GG],[GG;GG]],'color','black');
        
        text(x,GG,['\leftarrow','x=',num2str(xsol)],'horizontalalignment','left');
    end;
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if symbol==1
                plot(long(Iselect),lat(Iselect),'m*');  
            else
                plot(long(Iselect),lat(Iselect),'m.');      
            end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        obs=zeros(size(long,1),1);
    % box selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if BUTTON~=3 & BUTTON~=2 
        [obs,GG,xsol]=selectstat('gini',obs,variable,FuncF,FuncG,Xk,x);
        end;
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;

